import pandas as pd
import numpy as np
import json
import uuid
import pickle
import os

def merge_hotels(hotel_a, hotel_b, match_conf, near_miss_a, near_miss_b):
    canonical = {}
    canonical['id'] = str(uuid.uuid4())
    canonical['source_a_id'] = hotel_a['id']
    canonical['source_b_id'] = hotel_b['id']
    canonical['confidence'] = match_conf
    
    # Name: longer of the two
    name_a = str(hotel_a.get('name', ''))
    name_b = str(hotel_b.get('name', ''))
    canonical['name'] = name_a if len(name_a) >= len(name_b) else name_b
    
    # Address: prefer more complete string
    addr_a = str(hotel_a.get('address', ''))
    addr_b = str(hotel_b.get('address', ''))
    canonical['address'] = addr_a if len(addr_a) >= len(addr_b) else addr_b
    
    # Coordinates: A primary, B secondary
    canonical['lat'] = hotel_a.get('lat')
    canonical['lon'] = hotel_a.get('lon')
    canonical['b_lat'] = hotel_b.get('lat')
    canonical['b_lon'] = hotel_b.get('lon')
    
    # Stars
    stars_a = hotel_a.get('stars')
    stars_b = hotel_b.get('stars')
    if pd.isna(stars_a) and pd.isna(stars_b):
        canonical['stars'] = None
    elif pd.isna(stars_a):
        canonical['stars'] = stars_b
    elif pd.isna(stars_b):
        canonical['stars'] = stars_a
    elif stars_a == stars_b:
        canonical['stars'] = stars_a
    else:
        canonical['stars'] = f"{stars_a},{stars_b}"
        canonical['stars_conflict'] = True
        
    # Amenities (Union)
    am_a = set(hotel_a.get('amenities_list', []))
    am_b = set(hotel_b.get('amenities_list', []))
    canonical['amenities'] = list(am_a.union(am_b))
    
    # Images
    im_a = set(hotel_a.get('image_urls_list', []))
    im_b = set(hotel_b.get('image_urls_list', []))
    canonical['image_urls'] = list(im_a.union(im_b))
    
    # Near misses
    misses = []
    if near_miss_a: misses.append(near_miss_a)
    if near_miss_b: misses.append(near_miss_b)
    canonical['near_miss_candidates'] = misses
    
    return canonical

def create_single_canonical(hotel, source, miss):
    canonical = {}
    canonical['id'] = str(uuid.uuid4())
    if source == 'A':
        canonical['source_a_id'] = hotel['id']
        canonical['source_b_id'] = None
    else:
        canonical['source_a_id'] = None
        canonical['source_b_id'] = hotel['id']
        
    canonical['confidence'] = None
    canonical['name'] = hotel.get('name')
    canonical['address'] = hotel.get('address')
    canonical['lat'] = hotel.get('lat')
    canonical['lon'] = hotel.get('lon')
    canonical['b_lat'] = None
    canonical['b_lon'] = None
    canonical['stars'] = hotel.get('stars')
    canonical['amenities'] = hotel.get('amenities_list', [])
    canonical['image_urls'] = hotel.get('image_urls_list', [])
    
    if miss:
        canonical['near_miss_candidates'] = [miss]
    else:
        canonical['near_miss_candidates'] = []
        
    return canonical

def main():
    cache_dir = "data/cache"
    canon_dir = "data/canonical"
    os.makedirs(canon_dir, exist_ok=True)
    
    print("--- Merging Hotels ---")
    
    df_a = pd.read_pickle(f"{cache_dir}/hotels_a_processed.pkl").set_index('id')
    df_b = pd.read_pickle(f"{cache_dir}/hotels_b_processed.pkl").set_index('id')
    df_matches = pd.read_pickle(f"{cache_dir}/resolved_matches.pkl")
    
    with open(f"{cache_dir}/near_misses.pkl", "rb") as f:
        near_misses = pickle.load(f)
        
    canonical_hotels = []
    
    matched_a = set()
    matched_b = set()
    
    # Process Matches
    for _, row in df_matches.iterrows():
        a_id = row['a_id']
        b_id = row['b_id']
        conf = row['final_confidence']
        
        hotel_a = df_a.loc[a_id].to_dict()
        hotel_a['id'] = a_id
        hotel_b = df_b.loc[b_id].to_dict()
        hotel_b['id'] = b_id
        
        miss_a = near_misses.get(a_id)
        miss_b = near_misses.get(b_id)
        
        canon = merge_hotels(hotel_a, hotel_b, conf, miss_a, miss_b)
        canonical_hotels.append(canon)
        
        matched_a.add(a_id)
        matched_b.add(b_id)
        
    # Process Unmatched A
    for a_id, row in df_a.iterrows():
        if a_id not in matched_a:
            hotel_a = row.to_dict()
            hotel_a['id'] = a_id
            canon = create_single_canonical(hotel_a, 'A', near_misses.get(a_id))
            canonical_hotels.append(canon)
            
    # Process Unmatched B
    for b_id, row in df_b.iterrows():
        if b_id not in matched_b:
            hotel_b = row.to_dict()
            hotel_b['id'] = b_id
            canon = create_single_canonical(hotel_b, 'B', near_misses.get(b_id))
            canonical_hotels.append(canon)
            
    # Save canonical layer
    with open(f"{canon_dir}/canonical_hotels.json", "w") as f:
        json.dump(canonical_hotels, f, indent=2)
        
    print(f"Total Canonical Hotels: {len(canonical_hotels)}")
    print(f"Saved to {canon_dir}/canonical_hotels.json")
    
if __name__ == "__main__":
    main()

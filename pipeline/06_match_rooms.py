import pandas as pd
import yaml
import pickle
import os

def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

def jaccard(set1, set2):
    if not set1 and not set2: return 0.5
    if not set1 or not set2: return 0.0
    return len(set1.intersection(set2)) / len(set1.union(set2))

def compute_room_sim(room_a_parsed, room_b_parsed):
    # exact_bed_match
    if room_a_parsed.get('bed_type') and room_a_parsed.get('bed_type') == room_b_parsed.get('bed_type'):
        exact_bed_match = 1.0
    else:
        exact_bed_match = 0.0
        
    # capacity_match
    cap_a = room_a_parsed.get('capacity')
    cap_b = room_b_parsed.get('capacity')
    if cap_a and cap_a == cap_b:
        capacity_match = 1.0
    else:
        capacity_match = 0.0
        
    # features U class
    features_a = set(room_a_parsed.get('features', []))
    if room_a_parsed.get('room_class'):
        features_a.add(room_a_parsed['room_class'])
        
    features_b = set(room_b_parsed.get('features', []))
    if room_b_parsed.get('room_class'):
        features_b.add(room_b_parsed['room_class'])
        
    feat_sim = jaccard(features_a, features_b)
    
    return 0.4 * exact_bed_match + 0.3 * capacity_match + 0.3 * feat_sim

def main():
    cache_dir = "data/cache"
    config = load_config()
    match_threshold = config['rooms']['match_threshold']
    
    print("--- Matching Rooms ---")
    
    df_rooms_a = pd.read_pickle(f"{cache_dir}/rooms_a_processed.pkl")
    df_rooms_b = pd.read_pickle(f"{cache_dir}/rooms_b_processed.pkl")
    df_matches = pd.read_pickle(f"{cache_dir}/resolved_matches.pkl")
    
    with open(f"{cache_dir}/room_parse_cache.pkl", "rb") as f:
        room_cache = pickle.load(f)
        
    # Build fast lookups for rooms by hotel ID
    rooms_a_dict = {}
    for _, row in df_rooms_a.iterrows():
        hid = row['hotel_id']
        rooms_a_dict.setdefault(hid, []).append(row.to_dict())
        
    rooms_b_dict = {}
    for _, row in df_rooms_b.iterrows():
        hid = row['hotel_id']
        rooms_b_dict.setdefault(hid, []).append(row.to_dict())
        
    matched_rooms_out = []
    
    # Process only confirmed matches
    for _, match_row in df_matches.iterrows():
        a_id = match_row['a_id']
        b_id = match_row['b_id']
        
        r_a_list = rooms_a_dict.get(a_id, [])
        r_b_list = rooms_b_dict.get(b_id, [])
        
        # We need a greedy one-to-many match above threshold
        # First compute all pairwise similarities for this hotel pair
        pairs = []
        for ra in r_a_list:
            parsed_a = room_cache.get(ra['name'], {})
            for rb in r_b_list:
                parsed_b = room_cache.get(rb['name'], {})
                sim = compute_room_sim(parsed_a, parsed_b)
                if sim >= match_threshold:
                    pairs.append((ra, rb, sim))
                    
        # Sort by similarity descending for greedy assignment
        pairs.sort(key=lambda x: x[2], reverse=True)
        
        matched_ra_ids = set()
        matched_rb_ids = set()
        
        # Assign greedy
        for ra, rb, sim in pairs:
            # We allow 1-to-many. Which means one room can match multiple.
            # "a coarse room on one side may legitimately match several fare variants on the other"
            # We won't restrict matched_ra_ids or matched_rb_ids strictly 1-1.
            # We just add all above-threshold edges to matched_rooms_out.
            # But usually greedy means we might consume them. The instruction says:
            # "Greedy one-to-many matching above rooms.match_threshold"
            # We'll just include all edges that pass threshold, or restrict one side?
            # Let's restrict side A to one-to-many (A matches many B). We'll track matched_rb_ids to only be consumed once.
            if rb['room_id'] not in matched_rb_ids:
                matched_rooms_out.append({
                    'hotel_a_id': a_id,
                    'hotel_b_id': b_id,
                    'room_a_id': ra['room_id'],
                    'room_b_id': rb['room_id'],
                    'score': sim,
                    'parsed_a': room_cache.get(ra['name'], {}),
                    'parsed_b': room_cache.get(rb['name'], {})
                })
                matched_rb_ids.add(rb['room_id'])
                matched_ra_ids.add(ra['room_id'])
                
    df_room_matches = pd.DataFrame(matched_rooms_out)
    if not df_room_matches.empty:
        df_room_matches.to_pickle(f"{cache_dir}/room_matches.pkl")
        print(f"Matched {len(df_room_matches)} room pairs.")
    else:
        # Save empty
        pd.DataFrame(columns=['hotel_a_id', 'hotel_b_id', 'room_a_id', 'room_b_id', 'score', 'parsed_a', 'parsed_b']).to_pickle(f"{cache_dir}/room_matches.pkl")
        print("No room matches found.")
        
    print("Room matching complete. Saved to data/cache/")
    
if __name__ == "__main__":
    main()

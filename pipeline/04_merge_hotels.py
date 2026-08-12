import pandas as pd
import numpy as np
import json
import uuid
import pickle
import os
import sys
import re

# Add current directory to path to fix IDE and execution import errors
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import our new deduplicator
from amenity_normalizer import deduplicate_amenities
import bharataddress

def deduplicate_address(address: str) -> str:
    if not address or pd.isna(address):
        return None
    
    try:
        parsed = bharataddress.parse(address)
        components = []
        
        # Reconstruct the address cleanly using the recognized geographical hierarchy
        if parsed.building_name: components.append(parsed.building_name)
        if parsed.building_number: components.append(parsed.building_number)
        if parsed.sub_locality: components.append(parsed.sub_locality)
        if parsed.locality: components.append(parsed.locality)
        if parsed.landmark: components.append(parsed.landmark)
        if parsed.city: components.append(parsed.city)
        if parsed.district and parsed.district != parsed.city: components.append(parsed.district)
        if parsed.state: components.append(parsed.state)
        if parsed.pincode: components.append(parsed.pincode)
        
        if components:
            return ", ".join(components)
        return address # Fallback to original if parser fails to find components
    except Exception:
        return address # Fallback to original if parsing throws an error


def build_canonical(nodes, a_nodes, b_nodes, cluster_confidence, edges, df_a, df_b, near_misses):
    canonical = {}
    canonical['id'] = str(uuid.uuid4())
    
    # Track provenance
    canonical['source_a_id'] = a_nodes[0] if len(a_nodes) == 1 else ",".join(a_nodes) if len(a_nodes) > 1 else None
    canonical['source_b_id'] = b_nodes[0] if len(b_nodes) == 1 else ",".join(b_nodes) if len(b_nodes) > 1 else None
    
    canonical['confidence'] = cluster_confidence
    canonical['merge_edges'] = edges # For Graph RAG downstream!
    
    # Collect all hotel data dicts in this cluster
    cluster_hotels = []
    for a in a_nodes:
        if a in df_a.index:
            d = df_a.loc[a].to_dict()
            d['source'] = 'A'
            d['id'] = a
            cluster_hotels.append(d)
    for b in b_nodes:
        if b in df_b.index:
            d = df_b.loc[b].to_dict()
            d['source'] = 'B'
            d['id'] = b
            cluster_hotels.append(d)
            
    if not cluster_hotels:
        return None
        
    # Pick best name (longest)
    names = [str(h.get('name', '')) for h in cluster_hotels if pd.notna(h.get('name'))]
    canonical['name'] = max(names, key=len) if names else None
    
    # Pick best address and deduplicate components
    addrs = [str(h.get('address', '')) for h in cluster_hotels if pd.notna(h.get('address'))]
    if addrs:
        best_addr = max(addrs, key=len)
        canonical['address'] = deduplicate_address(best_addr)
    else:
        canonical['address'] = None
    
    # Coords (Prefer A's, then B's)
    a_coords = [(h['lat'], h['lon']) for h in cluster_hotels if h['source'] == 'A' and pd.notna(h.get('lat'))]
    b_coords = [(h['lat'], h['lon']) for h in cluster_hotels if h['source'] == 'B' and pd.notna(h.get('lat'))]
    
    if a_coords:
        canonical['lat'] = a_coords[0][0]
        canonical['lon'] = a_coords[0][1]
    elif b_coords:
        canonical['lat'] = b_coords[0][0]
        canonical['lon'] = b_coords[0][1]
        
    if b_coords:
        canonical['b_lat'] = b_coords[0][0]
        canonical['b_lon'] = b_coords[0][1]
    else:
        canonical['b_lat'] = None
        canonical['b_lon'] = None
        
    # Stars
    stars = list(set([h['stars'] for h in cluster_hotels if pd.notna(h.get('stars'))]))
    if not stars:
        canonical['stars'] = None
    elif len(stars) == 1:
        canonical['stars'] = stars[0]
    else:
        canonical['stars'] = ",".join(map(str, stars))
        canonical['stars_conflict'] = True
        
    # Amenities
    raw_amenities = []
    for h in cluster_hotels:
        raw_amenities.extend(h.get('amenities_list', []))
    canonical['amenities'] = deduplicate_amenities(raw_amenities)
    
    # Images (Honest merge of all provided URLs)
    all_images = []
    seen = set()
    for h in cluster_hotels:
        for img in h.get('image_urls_list', []):
            if img not in seen:
                seen.add(img)
                all_images.append(img)
    canonical['image_urls'] = all_images
    
    misses = []
    for h in cluster_hotels:
        m = near_misses.get(h['id'], [])
        if isinstance(m, list):
            misses.extend(m)
        elif m:
            misses.append(m)
    canonical['near_miss_candidates'] = misses
    
    return canonical

def main():
    cache_dir = "data/cache"
    canon_dir = "data/canonical"
    os.makedirs(canon_dir, exist_ok=True)
    
    print("--- Merging Hotels ---")
    
    df_a = pd.read_pickle(f"{cache_dir}/hotels_a_processed.pkl").set_index('id')
    df_b = pd.read_pickle(f"{cache_dir}/hotels_b_processed.pkl").set_index('id')
    
    with open(f"{cache_dir}/canonical_clusters.pkl", "rb") as f:
        canonical_clusters = pickle.load(f)
        
    with open(f"{cache_dir}/near_misses.pkl", "rb") as f:
        near_misses = pickle.load(f)
        
    canonical_hotels = []
    
    matched_a = set()
    matched_b = set()
    
    # Build from clusters
    for cluster in canonical_clusters:
        c = build_canonical(
            cluster['nodes'], 
            cluster['a_nodes'], 
            cluster['b_nodes'], 
            cluster['cluster_confidence'],
            cluster['edges'],
            df_a, df_b, near_misses
        )
        if c:
            canonical_hotels.append(c)
        matched_a.update(cluster['a_nodes'])
        matched_b.update(cluster['b_nodes'])
        
    # Unmatched Singletons
    for a_id, row in df_a.iterrows():
        if a_id not in matched_a:
            c = build_canonical([a_id], [a_id], [], None, [], df_a, df_b, near_misses)
            if c: canonical_hotels.append(c)
            
    for b_id, row in df_b.iterrows():
        if b_id not in matched_b:
            c = build_canonical([b_id], [], [b_id], None, [], df_a, df_b, near_misses)
            if c: canonical_hotels.append(c)
            
    # Save canonical layer
    with open(f"{canon_dir}/canonical_hotels.json", "w") as f:
        json.dump(canonical_hotels, f, indent=2)
        
    print(f"Total Canonical Hotels: {len(canonical_hotels)}")
    print(f"Saved to {canon_dir}/canonical_hotels.json")
    
if __name__ == "__main__":
    main()

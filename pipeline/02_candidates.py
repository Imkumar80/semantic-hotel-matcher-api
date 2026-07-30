import pandas as pd
import numpy as np
import yaml
import os
from sklearn.neighbors import BallTree
from rapidfuzz import process, fuzz

def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

# Haversine distance in meters
def get_haversine_radius(meters):
    # Earth radius ~ 6371000 meters
    return meters / 6371000.0

def main():
    cache_dir = "data/cache"
    
    print("--- Candidate Generation ---")
    
    # Load processed data
    df_a = pd.read_pickle(f"{cache_dir}/hotels_a_processed.pkl")
    df_b = pd.read_pickle(f"{cache_dir}/hotels_b_processed.pkl")
    
    config = load_config()
    radius_meters = config['matching']['radius_meters']
    max_candidates_fallback = config['matching']['max_candidates_per_hotel']
    
    # Filter B for valid coords for BallTree
    df_b_valid = df_b[df_b['valid_coords']].copy()
    
    # Convert lat/lon to radians for Haversine
    df_b_valid['lat_rad'] = np.radians(df_b_valid['lat'].astype(float))
    df_b_valid['lon_rad'] = np.radians(df_b_valid['lon'].astype(float))
    
    # Build BallTree on B (valid coords)
    print("Building BallTree on Supplier B coordinates...")
    tree = BallTree(df_b_valid[['lat_rad', 'lon_rad']], metric='haversine')
    
    candidates = []
    
    fallback_count = 0
    # For fallback string matching, keep all B names ready
    b_names = df_b['normalized_name'].tolist()
    b_ids = df_b['id'].tolist()
    
    # Iterate through A
    for idx, row in df_a.iterrows():
        a_id = row['id']
        if row['valid_coords']:
            # Query KDTree
            lat_rad = np.radians(float(row['lat']))
            lon_rad = np.radians(float(row['lon']))
            
            # radius query
            radius_rad = get_haversine_radius(radius_meters)
            indices = tree.query_radius([[lat_rad, lon_rad]], r=radius_rad)[0]
            
            for i in indices:
                b_id = df_b_valid.iloc[i]['id']
                candidates.append((a_id, b_id))
        else:
            # Fallback to Name blocking (RapidFuzz)
            fallback_count += 1
            a_name = row['normalized_name']
            if not a_name:
                continue
                
            # Use process.extract to get top K matches
            matches = process.extract(
                a_name, 
                b_names, 
                scorer=fuzz.token_sort_ratio, 
                limit=max_candidates_fallback
            )
            for match in matches:
                # match format: (name, score, index)
                b_idx = match[2]
                b_id = b_ids[b_idx]
                candidates.append((a_id, b_id))
                
    # Deduplicate candidates (just in case)
    candidates_set = set(candidates)
    
    print(f"Total Candidate Pairs: {len(candidates_set)}")
    print(f"Avg candidates/hotel (A): {len(candidates_set) / len(df_a):.2f}")
    print(f"Hotels using Name-Fallback (missing/bad coords): {fallback_count}")
    
    # Save candidates
    df_candidates = pd.DataFrame(list(candidates_set), columns=['a_id', 'b_id'])
    df_candidates.to_pickle(f"{cache_dir}/candidate_pairs.pkl")
    print("Candidates saved to data/cache/candidate_pairs.pkl")

if __name__ == "__main__":
    main()

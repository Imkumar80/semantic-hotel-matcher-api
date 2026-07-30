import pandas as pd
import numpy as np
import yaml
import os
import torch
from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import pickle

def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000 # Earth radius in meters
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c

def normalize_address(addr: str) -> str:
    if pd.isna(addr):
        return ""
    addr = str(addr).lower()
    addr = addr.replace(',', ' ').replace('.', ' ').replace('-', ' ')
    addr = ' '.join(addr.split())
    return addr

def compute_amenity_score(am1, am2):
    if not am1 and not am2:
        return 0.5 # Neutral if both missing
    if not am1 or not am2:
        return 0.0
    set1 = set(am1)
    set2 = set(am2)
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0

def embed_strings(strings, model_name, cache_path):
    if os.path.exists(cache_path):
        print(f"Loading embeddings from {cache_path}")
        with open(cache_path, 'rb') as f:
            return pickle.load(f)
    
    print(f"Computing embeddings using {model_name}...")
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = SentenceTransformer(model_name, device=device)
    embeddings = model.encode(strings, batch_size=256, show_progress_bar=True)
    with open(cache_path, 'wb') as f:
        pickle.dump(embeddings, f)
    return embeddings

def main():
    cache_dir = "data/cache"
    config = load_config()
    
    print("--- Scoring Candidates ---")
    
    df_a = pd.read_pickle(f"{cache_dir}/hotels_a_processed.pkl")
    df_b = pd.read_pickle(f"{cache_dir}/hotels_b_processed.pkl")
    df_candidates = pd.read_pickle(f"{cache_dir}/candidate_pairs.pkl")
    
    df_a = df_a.set_index('id')
    df_b = df_b.set_index('id')
    
    # Pre-compute address normalization
    df_a['norm_addr'] = df_a['address'].apply(normalize_address)
    df_b['norm_addr'] = df_b['address'].apply(normalize_address)
    
    # Pre-compute combined string for embeddings
    df_a['embed_str'] = df_a['normalized_name'] + " " + df_a['norm_addr']
    df_b['embed_str'] = df_b['normalized_name'] + " " + df_b['norm_addr']
    
    # Get unique strings and compute embeddings
    unique_strings_a = df_a['embed_str'].unique().tolist()
    unique_strings_b = df_b['embed_str'].unique().tolist()
    all_unique_strings = list(set(unique_strings_a + unique_strings_b))
    
    emb_model = config['models']['embedding_model']
    embeddings_cache_path = f"{cache_dir}/hotel_embeddings.pkl"
    embeddings_matrix = embed_strings(all_unique_strings, emb_model, embeddings_cache_path)
    
    # Create mapping from string to embedding index
    str_to_idx = {s: i for i, s in enumerate(all_unique_strings)}
    
    radius_meters = config['matching']['radius_meters']
    weights = config['weights']
    
    results = []
    
    print(f"Scoring {len(df_candidates)} pairs...")
    
    for _, row in df_candidates.iterrows():
        a_id = row['a_id']
        b_id = row['b_id']
        
        hotel_a = df_a.loc[a_id]
        hotel_b = df_b.loc[b_id]
        
        # 1. Name Score
        name_score = fuzz.token_sort_ratio(hotel_a['normalized_name'], hotel_b['normalized_name']) / 100.0
        
        # 2. Address Score
        addr_score = fuzz.token_set_ratio(hotel_a['norm_addr'], hotel_b['norm_addr']) / 100.0
        
        # 3. Distance Score
        if hotel_a['valid_coords'] and hotel_b['valid_coords']:
            dist_m = haversine_distance(hotel_a['lat'], hotel_a['lon'], hotel_b['lat'], hotel_b['lon'])
            dist_score = max(0.0, 1.0 - (dist_m / radius_meters))
        else:
            dist_score = 0.0
            
        # 4. Amenity Score
        amenity_score = compute_amenity_score(hotel_a.get('amenities_list', []), hotel_b.get('amenities_list', []))
        
        # 5. Embedding Score
        idx_a = str_to_idx[hotel_a['embed_str']]
        idx_b = str_to_idx[hotel_b['embed_str']]
        emb_a = embeddings_matrix[idx_a].reshape(1, -1)
        emb_b = embeddings_matrix[idx_b].reshape(1, -1)
        emb_score = cosine_similarity(emb_a, emb_b)[0][0]
        # constrain between 0 and 1
        emb_score = max(0.0, min(1.0, float(emb_score)))
        
        # Final weighted score
        final_score = (
            weights['name'] * name_score +
            weights['embedding'] * emb_score +
            weights['address'] * addr_score +
            weights['distance'] * dist_score +
            weights['amenities'] * amenity_score
        )
        
        results.append({
            'a_id': a_id,
            'b_id': b_id,
            'name_score': name_score,
            'address_score': addr_score,
            'distance_score': dist_score,
            'amenity_score': amenity_score,
            'embedding_score': emb_score,
            'final_score': final_score
        })
        
    df_scored = pd.DataFrame(results)
    df_scored.to_pickle(f"{cache_dir}/scored_pairs.pkl")
    print(f"Scored {len(df_scored)} pairs. Saved to data/cache/scored_pairs.pkl")

if __name__ == "__main__":
    main()

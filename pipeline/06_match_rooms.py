import pandas as pd
import yaml
import pickle
import os

def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

from rapidfuzz import fuzz
import re

def normalize_room_name(name):
    # Standardize common abbreviations before fuzzy matching
    name = str(name).lower()
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    name = name.replace(' sgl ', ' single ').replace(' dbl ', ' double ').replace(' twi ', ' twin ')
    name = name.replace(' std ', ' standard ').replace(' dlx ', ' deluxe ').replace(' sup ', ' superior ')
    name = name.replace(' 1k ', ' king ').replace(' 2q ', ' queen ')
    return ' '.join(name.split())

def compute_room_sim(room_a_name, room_b_name, room_a_parsed, room_b_parsed):
    # Industry Standard: Token Set Ratio on normalized strings
    norm_a = normalize_room_name(room_a_name)
    norm_b = normalize_room_name(room_b_name)
    
    base_score = fuzz.token_set_ratio(norm_a, norm_b) / 100.0
    
    # Optional Boosts for structured data if available
    if room_a_parsed.get('bed_type') and room_b_parsed.get('bed_type'):
        if room_a_parsed['bed_type'] == room_b_parsed['bed_type']:
            base_score = min(1.0, base_score + 0.1) # Boost for exact bed match
        else:
            base_score = base_score * 0.8 # Penalize conflicting beds
            
    if room_a_parsed.get('capacity') and room_b_parsed.get('capacity'):
        if room_a_parsed['capacity'] == room_b_parsed['capacity']:
            base_score = min(1.0, base_score + 0.1) # Boost for exact capacity match
        else:
            base_score = base_score * 0.7 # Heavy penalty for conflicting capacity
            
    if room_a_parsed.get('meal_plan') and room_b_parsed.get('meal_plan'):
        if room_a_parsed['meal_plan'] == room_b_parsed['meal_plan']:
            base_score = min(1.0, base_score + 0.1) # Boost for exact meal match
        else:
            base_score = base_score * 0.7 # Heavy penalty for conflicting meal plans
            
    return base_score

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
                sim = compute_room_sim(ra['name'], rb['name'], parsed_a, parsed_b)
                if sim >= match_threshold:
                    pairs.append((ra, rb, sim))
                    
        # Sort by similarity descending for greedy assignment
        pairs.sort(key=lambda x: x[2], reverse=True)
        
        matched_ra_ids = set()
        matched_rb_ids = set()
        
        import networkx as nx
        B = nx.Graph()
        
        # Add nodes and edges to bipartite graph
        for ra, rb, sim in pairs:
            # We prefix to ensure disjoint sets for bipartite matching
            a_node = f"A_{ra['room_id']}"
            b_node = f"B_{rb['room_id']}"
            B.add_edge(a_node, b_node, weight=sim, ra=ra, rb=rb)
            
        # Compute optimal 1-to-1 matching (prevents greedy suboptimal choices)
        matching = nx.max_weight_matching(B, maxcardinality=False)
        
        for u, v in matching:
            # max_weight_matching returns edges as (u, v) in no particular order
            a_node = u if str(u).startswith("A_") else v
            b_node = v if str(u).startswith("A_") else u
            
            sim = B[a_node][b_node]['weight']
            ra = B[a_node][b_node]['ra']
            rb = B[a_node][b_node]['rb']
            
            matched_rooms_out.append({
                'hotel_a_id': a_id,
                'hotel_b_id': b_id,
                'room_a_id': ra['room_id'],
                'room_b_id': rb['room_id'],
                'score': sim,
                'parsed_a': room_cache.get(ra['name'], {}),
                'parsed_b': room_cache.get(rb['name'], {})
            })
                
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

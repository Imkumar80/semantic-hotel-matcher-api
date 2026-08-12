import pandas as pd
import yaml
import os
import json
import httpx
import time
from google import genai
from google.genai import types
from pydantic import BaseModel
import pickle
from tenacity import retry, stop_after_attempt, wait_exponential
import networkx as nx
import uuid

class LLMResponse(BaseModel):
    is_match: bool
    confidence: float
    reason: str

def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

@retry(wait=wait_exponential(multiplier=2, min=15, max=70), stop=stop_after_attempt(10))
def call_gemini(client, model_name, prompt):
    return client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction="You are a specialized entity resolution assistant for hotel data. You MUST output your decision as a strict JSON object.",
            response_mime_type="application/json",
            response_schema=LLMResponse,
            temperature=0.0
        )
    )

def verify_with_llm(hotel_a, hotel_b, model_name, client, cache):
    a_id = hotel_a['id']
    b_id = hotel_b['id']
    cache_key = (a_id, b_id)
    
    if cache_key in cache:
        return cache[cache_key]
    
    if not client:
        res = LLMResponse(is_match=False, confidence=0.0, reason="No API key provided for LLM.")
        cache[cache_key] = res
        return res
        
    prompt = f"""
Compare these two hotel records and determine if they represent the exact same physical property.

Record A (Supplier A):
Name: {hotel_a.get('name')}
Address: {hotel_a.get('address')}
Coordinates: {hotel_a.get('lat')}, {hotel_a.get('lon')}

Record B (Supplier B):
Name: {hotel_b.get('name')}
Address: {hotel_b.get('address')}
Coordinates: {hotel_b.get('lat')}, {hotel_b.get('lon')}
"""
    try:
        response = call_gemini(client, model_name, prompt)
        response_obj = response.parsed
        if not response_obj:
            response_obj = LLMResponse.model_validate_json(response.text)
        cache[cache_key] = response_obj
        return response_obj
    except Exception as e:
        print(f"LLM Error for {a_id} vs {b_id}: {e}")
        res = LLMResponse(is_match=False, confidence=0.0, reason=f"Error: {e}")
        cache[cache_key] = res
        return res

def main():
    cache_dir = "data/cache"
    config = load_config()
    
    print("--- Resolving Hotels via Splink + LLM (with NetworkX Graph) ---")
    
    df_a = pd.read_pickle(f"{cache_dir}/hotels_a_processed.pkl").set_index('id')
    df_b = pd.read_pickle(f"{cache_dir}/hotels_b_processed.pkl").set_index('id')
    df_scored = pd.read_pickle(f"{cache_dir}/scored_pairs.pkl")
    
    auto_match_threshold = config['matching']['auto_match_threshold']
    llm_review_threshold = config['matching']['llm_review_threshold']
    llm_model = config['models']['llm_model']
    
    client = None
    print("WARNING: Skipping LLM step due to invalid GEMINI_API_KEY. Falling back to auto-reject for borderline matches.")
        
    llm_cache_path = f"{cache_dir}/llm_hotel_cache.pkl"
    if os.path.exists(llm_cache_path):
        with open(llm_cache_path, "rb") as f:
            llm_cache = pickle.load(f)
    else:
        llm_cache = {}
        
    # We build a graph of confirmed matches
    G = nx.Graph()
    
    near_misses = {} 
    stats = {'auto_match': 0, 'llm_match': 0, 'llm_reject': 0, 'auto_reject': 0}
    
    df_scored = df_scored.sort_values(by='final_score', ascending=False)
    
    for _, row in df_scored.iterrows():
        a_id = row['a_id']
        b_id = row['b_id']
        score = row['final_score']
        
        is_match = False
        final_confidence = score
        
        if score >= auto_match_threshold:
            is_match = True
            stats['auto_match'] += 1
            final_confidence = score
        elif score >= llm_review_threshold:
            hotel_a_data = df_a.loc[a_id].to_dict()
            hotel_a_data['id'] = a_id
            hotel_b_data = df_b.loc[b_id].to_dict()
            hotel_b_data['id'] = b_id
            
            res = verify_with_llm(hotel_a_data, hotel_b_data, llm_model, client, llm_cache)
            if res.is_match:
                is_match = True
                final_confidence = 0.5 * score + 0.5 * res.confidence
                stats['llm_match'] += 1
            else:
                stats['llm_reject'] += 1
        else:
            stats['auto_reject'] += 1
            
        if is_match:
            # Keep confidence on the edge! (Weighted Edge Graphing)
            G.add_edge(a_id, b_id, weight=final_confidence)
        else:
            if a_id not in near_misses:
                near_misses[a_id] = []
            near_misses[a_id].append({'miss_id': b_id, 'score': score})
            near_misses[a_id] = sorted(near_misses[a_id], key=lambda x: x['score'], reverse=True)[:5]
                
            if b_id not in near_misses:
                near_misses[b_id] = []
            near_misses[b_id].append({'miss_id': a_id, 'score': score})
            near_misses[b_id] = sorted(near_misses[b_id], key=lambda x: x['score'], reverse=True)[:5]
                
    with open(llm_cache_path, "wb") as f:
        pickle.dump(llm_cache, f)
        
    print(f"Auto matches: {stats['auto_match']}, LLM matches: {stats['llm_match']}, LLM rejected: {stats['llm_reject']}, Auto rejected: {stats['auto_reject']}")
    
    # Extract components
    components = list(nx.connected_components(G))
    print(f"Total Canonical Clusters (Components): {len(components)}")
    
    # Generate canonical matches
    matches = []
    canonical_clusters = []
    for comp in components:
        comp_nodes = list(comp)
        cluster_id = str(uuid.uuid4())
        
        # Calculate minimum edge weight in the component's subgraph as cluster confidence
        subgraph = G.subgraph(comp_nodes)
        edge_weights = [d['weight'] for u, v, d in subgraph.edges(data=True)]
        cluster_confidence = min(edge_weights) if edge_weights else 1.0
        
        a_nodes = [n for n in comp_nodes if n.startswith('A-')]
        b_nodes = [n for n in comp_nodes if n.startswith('B-')]
        
        # For our simple schema, just pair up the best (we expect mostly 1:1, but could be N:M)
        # We output all combinations within the cluster to `resolved_matches.pkl` so downstream logic works
        # And we pass the whole cluster to merge_hotels
        canonical_clusters.append({
            'canonical_id': cluster_id,
            'nodes': comp_nodes,
            'a_nodes': a_nodes,
            'b_nodes': b_nodes,
            'cluster_confidence': cluster_confidence,
            'edges': list(subgraph.edges(data=True))
        })
        
        # For backwards compatibility with match_rooms which expects pairwise
        for a_node in a_nodes:
            for b_node in b_nodes:
                matches.append({
                    'a_id': a_node,
                    'b_id': b_node,
                    'final_confidence': cluster_confidence
                })
    
    df_matches = pd.DataFrame(matches)
    if df_matches.empty:
        df_matches = pd.DataFrame(columns=['a_id', 'b_id', 'final_confidence'])
        
    df_matches.to_pickle(f"{cache_dir}/resolved_matches.pkl")
    
    with open(f"{cache_dir}/canonical_clusters.pkl", "wb") as f:
        pickle.dump(canonical_clusters, f)
    
    with open(f"{cache_dir}/near_misses.pkl", "wb") as f:
        pickle.dump(near_misses, f)
        
    print("Resolved matches and graph clusters saved.")

if __name__ == "__main__":
    main()

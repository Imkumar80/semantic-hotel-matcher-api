import pandas as pd
import numpy as np
import yaml
import os
import json
from google import genai
from google.genai import types
from pydantic import BaseModel
import pickle

class LLMResponse(BaseModel):
    is_match: bool
    confidence: float
    reason: str

def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

def verify_with_llm(hotel_a, hotel_b, model_name, client, cache):
    a_id = hotel_a['id']
    b_id = hotel_b['id']
    cache_key = (a_id, b_id)
    
    if cache_key in cache:
        return cache[cache_key]
    
    if not client:
        # Fallback if no API key is provided
        res = LLMResponse(is_match=False, confidence=0.0, reason="No API key provided for LLM.")
        cache[cache_key] = res
        return res
        
    prompt = f"""
Compare these two hotel records and determine if they represent the exact same physical property.

Record A (Supplier A):
Name: {hotel_a.get('name')}
Address: {hotel_a.get('address')}
Coordinates: {hotel_a.get('lat')}, {hotel_a.get('lon')}
Stars: {hotel_a.get('stars')}

Record B (Supplier B):
Name: {hotel_b.get('name')}
Address: {hotel_b.get('address')}
Coordinates: {hotel_b.get('lat')}, {hotel_b.get('lon')}
Stars: {hotel_b.get('stars')}
"""
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a specialized entity resolution assistant for hotel data. You MUST output your decision as a strict JSON object.",
                response_mime_type="application/json",
                response_schema=LLMResponse,
                temperature=0.0
            )
        )
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
    
    print("--- Resolving Hotels ---")
    
    df_a = pd.read_pickle(f"{cache_dir}/hotels_a_processed.pkl").set_index('id')
    df_b = pd.read_pickle(f"{cache_dir}/hotels_b_processed.pkl").set_index('id')
    df_scored = pd.read_pickle(f"{cache_dir}/scored_pairs.pkl")
    
    auto_match_threshold = config['matching']['auto_match_threshold']
    llm_review_threshold = config['matching']['llm_review_threshold']
    llm_model = config['models']['llm_model']
    
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY")) if os.environ.get("GEMINI_API_KEY") else None
    if not client:
        print("WARNING: GEMINI_API_KEY not set. LLM verification will default to NO MATCH.")
        
    llm_cache_path = f"{cache_dir}/llm_hotel_cache.pkl"
    if os.path.exists(llm_cache_path):
        with open(llm_cache_path, "rb") as f:
            llm_cache = pickle.load(f)
    else:
        llm_cache = {}
        
    matches = []
    near_misses = {} # map a_id -> best near miss, b_id -> best near miss
    
    stats = {'auto_match': 0, 'llm_match': 0, 'llm_reject': 0, 'auto_reject': 0}
    
    # Sort scored descending so we process best matches first
    df_scored = df_scored.sort_values(by='final_score', ascending=False)
    
    # Track which hotels are already matched
    matched_a = set()
    matched_b = set()
    
    for _, row in df_scored.iterrows():
        a_id = row['a_id']
        b_id = row['b_id']
        score = row['final_score']
        
        # If either is already matched to something else, skip it.
        # This enforces 1-to-1 matching greedily.
        if a_id in matched_a or b_id in matched_b:
            # Maybe keep as near miss if not matched? We handle near miss below.
            continue
            
        is_match = False
        final_confidence = score
        
        if score >= auto_match_threshold:
            is_match = True
            stats['auto_match'] += 1
        elif score >= llm_review_threshold:
            # LLM Verification
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
            matched_a.add(a_id)
            matched_b.add(b_id)
            matches.append({
                'a_id': a_id,
                'b_id': b_id,
                'heuristic_score': score,
                'final_confidence': final_confidence
            })
        else:
            # Update near miss (only track one best near miss per hotel)
            # Since we iterate descending by score, the first near miss we see is the best one.
            if a_id not in near_misses:
                near_misses[a_id] = {'miss_id': b_id, 'score': score}
            if b_id not in near_misses:
                near_misses[b_id] = {'miss_id': a_id, 'score': score}
                
    # Save cache
    with open(llm_cache_path, "wb") as f:
        pickle.dump(llm_cache, f)
        
    print(f"Total Matches: {len(matches)}")
    print(f"Auto matches: {stats['auto_match']}")
    print(f"LLM matches: {stats['llm_match']}")
    print(f"LLM rejected: {stats['llm_reject']}")
    print(f"Auto rejected: {stats['auto_reject']}")
    
    # Save results
    df_matches = pd.DataFrame(matches)
    df_matches.to_pickle(f"{cache_dir}/resolved_matches.pkl")
    
    with open(f"{cache_dir}/near_misses.pkl", "wb") as f:
        pickle.dump(near_misses, f)
        
    print("Resolved matches and near misses saved to data/cache/")

if __name__ == "__main__":
    main()

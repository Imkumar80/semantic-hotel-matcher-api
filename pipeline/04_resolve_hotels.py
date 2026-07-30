import pandas as pd
import numpy as np
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

class LLMResponse(BaseModel):
    is_match: bool
    confidence: float
    reason: str

def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

OSM_CACHE_FILE = "data/osm_cache.json"

def fetch_osm_context(lat, lon):
    if not lat or not lon:
        return "No coordinates provided."
        
    if os.path.exists(OSM_CACHE_FILE):
        with open(OSM_CACHE_FILE, "r") as f:
            cache = json.load(f)
    else:
        cache = {}
        
    cache_key = f"{lat},{lon}"
    if cache_key in cache:
        return cache[cache_key]
        
    time.sleep(1.2) # Rate limit (1 req/sec)
    
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "format": "json",
        "lat": lat,
        "lon": lon,
        "zoom": 18
    }
    headers = {
        "User-Agent": "SemanticHotelMatcher/1.0 (careers@heyaway.ai)"
    }
    try:
        r = httpx.get(url, params=params, headers=headers, timeout=10.0)
        r.raise_for_status()
        data = r.json()
        
        display_name = data.get("display_name", "Unknown Address")
        address_dict = data.get("address", {})
        
        context = f"Full Address: {display_name}\n"
        if "hotel" in address_dict or "tourism" in address_dict or "building" in address_dict:
            building_name = address_dict.get("hotel", address_dict.get("tourism", address_dict.get("building")))
            if building_name:
                context += f"Building Name at location: {building_name}\n"
        
        cache[cache_key] = context
        with open(OSM_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
            
        return context
    except Exception as e:
        print(f"OSM fetch error for {lat},{lon}: {e}")
        return f"OSM lookup failed: {e}"

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
        
    osm_a = fetch_osm_context(hotel_a.get('lat'), hotel_a.get('lon'))
    osm_b = fetch_osm_context(hotel_b.get('lat'), hotel_b.get('lon'))
        
    prompt = f"""
Compare these two hotel records and determine if they represent the exact same physical property.
Use the provided OSM (OpenStreetMap) context to resolve discrepancies in names or addresses.

Record A (Supplier A):
Name: {hotel_a.get('name')}
Address: {hotel_a.get('address')}
Coordinates: {hotel_a.get('lat')}, {hotel_a.get('lon')}
Stars: {hotel_a.get('stars')}
OSM Context at Coord A:
{osm_a}

Record B (Supplier B):
Name: {hotel_b.get('name')}
Address: {hotel_b.get('address')}
Coordinates: {hotel_b.get('lat')}, {hotel_b.get('lon')}
Stars: {hotel_b.get('stars')}
OSM Context at Coord B:
{osm_b}
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
    
    print("--- Resolving Hotels via Heuristics + LLM (with OSM Context) ---")
    
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
    near_misses = {} 
    
    stats = {'auto_match': 0, 'llm_match': 0, 'llm_reject': 0, 'auto_reject': 0}
    
    df_scored = df_scored.sort_values(by='final_score', ascending=False)
    
    matched_a = set()
    matched_b = set()
    
    print(f"Processing {len(df_scored)} pairs. Auto Match >= {auto_match_threshold}, LLM Review >= {llm_review_threshold}")
    
    for _, row in df_scored.iterrows():
        a_id = row['a_id']
        b_id = row['b_id']
        score = row['final_score']
        
        if a_id in matched_a or b_id in matched_b:
            continue
            
        is_match = False
        final_confidence = score
        
        if score >= auto_match_threshold:
            is_match = True
            stats['auto_match'] += 1
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
            matched_a.add(a_id)
            matched_b.add(b_id)
            matches.append({
                'a_id': a_id,
                'b_id': b_id,
                'heuristic_score': score,
                'final_confidence': final_confidence
            })
        else:
            if a_id not in near_misses:
                near_misses[a_id] = {'miss_id': b_id, 'score': score}
            if b_id not in near_misses:
                near_misses[b_id] = {'miss_id': a_id, 'score': score}
                
    with open(llm_cache_path, "wb") as f:
        pickle.dump(llm_cache, f)
        
    print(f"Total Matches: {len(matches)}")
    print(f"Auto matches: {stats['auto_match']}")
    print(f"LLM matches: {stats['llm_match']}")
    print(f"LLM rejected: {stats['llm_reject']}")
    print(f"Auto rejected: {stats['auto_reject']}")
    
    df_matches = pd.DataFrame(matches)
    df_matches.to_pickle(f"{cache_dir}/resolved_matches.pkl")
    
    with open(f"{cache_dir}/near_misses.pkl", "wb") as f:
        pickle.dump(near_misses, f)
        
    print("Resolved matches and near misses saved to data/cache/")

if __name__ == "__main__":
    main()

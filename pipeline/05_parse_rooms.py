import pandas as pd
import numpy as np
import yaml
import os
import json
import re
import pickle
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from flashtext import KeywordProcessor
from rapidfuzz import process, fuzz

class ParsedRoom(BaseModel):
    capacity: Optional[int]
    bed_type: Optional[str]
    view: Optional[str]
    features: List[str]
    room_class: Optional[str]

class BatchParsedRoom(BaseModel):
    results: List[ParsedRoom]

def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

# Initialize FlashText Taxonomy
kp = KeywordProcessor(case_sensitive=False)

# Bed Types
for b in ['single', 'twin', 'double', 'king', 'queen', 'bunk', 'sofa bed']:
    kp.add_keyword(b, ('bed_type', b.title().replace(' Bed', '')))

# Room Class
for c in ['standard', 'std', 'deluxe', 'dlx', 'superior', 'sup', 'executive', 'exec', 'premium', 'suite', 'studio', 'villa', 'apartment']:
    canonical = c.title()
    if c == 'std': canonical = 'Standard'
    if c == 'dlx': canonical = 'Deluxe'
    if c == 'sup': canonical = 'Superior'
    if c == 'exec': canonical = 'Executive'
    kp.add_keyword(c, ('room_class', canonical))

# Views
for v in ['city view', 'city', 'pool view', 'pool', 'sea view', 'sea', 'ocean view', 'ocean', 'garden view', 'garden', 'lake view', 'lake']:
    canonical = v.title().replace(' View', '')
    if canonical == 'Ocean': canonical = 'Sea'
    kp.add_keyword(v, ('view', canonical))

# Features
for f in ['breakfast', 'balcony', 'air conditioning', 'ac', 'wi-fi', 'wifi', 'jacuzzi', 'kitchen', 'patio']:
    canonical = f.title()
    if f in ['ac', 'air conditioning']: canonical = 'AC'
    if f in ['wifi', 'wi-fi']: canonical = 'WiFi'
    kp.add_keyword(f, ('features', canonical))

# Capacities
for i in range(1, 10):
    kp.add_keyword(f'{i} adult', ('capacity', i))
    kp.add_keyword(f'{i} adults', ('capacity', i))

FUZZ_VOCAB = {
    'bed_type': ['single', 'twin', 'double', 'king', 'queen', 'bunk', 'sofa bed'],
    'room_class': ['standard', 'deluxe', 'superior', 'executive', 'premium', 'suite', 'studio', 'villa', 'apartment'],
    'view': ['city view', 'pool view', 'sea view', 'ocean view', 'garden view', 'lake view'],
    'features': ['breakfast', 'balcony', 'air conditioning', 'wifi', 'jacuzzi', 'kitchen', 'patio']
}

def smart_extract(name: str):
    parsed = {
        'capacity': None,
        'bed_type': None,
        'view': None,
        'features': set(),
        'room_class': None
    }
    
    found = kp.extract_keywords(name)
    for category, value in found:
        if category == 'features':
            parsed[category].add(value)
        elif parsed[category] is None:
            parsed[category] = value
            
    if parsed['capacity'] is None and parsed['bed_type']:
        if parsed['bed_type'] == 'Single':
            parsed['capacity'] = 1
        else:
            parsed['capacity'] = 2

    tokens = re.findall(r'\b[a-zA-Z]{3,}\b', name.lower())
    for token in tokens:
        for category, options in FUZZ_VOCAB.items():
            if parsed[category] is None or category == 'features':
                best_match = process.extractOne(token, options, scorer=fuzz.ratio)
                if best_match and best_match[1] >= 85:
                    val = best_match[0].title()
                    if category == 'features':
                        if val == 'Air Conditioning': val = 'AC'
                        if val == 'Wifi': val = 'WiFi'
                        parsed[category].add(val)
                    else:
                        if parsed[category] is None:
                            if val in ['Sea View', 'Ocean View']: val = 'Sea'
                            elif val.endswith(' View'): val = val.replace(' View', '')
                            parsed[category] = val

    is_resolved = (parsed['room_class'] is not None) or (parsed['bed_type'] is not None)
    parsed['features'] = list(parsed['features'])
    return is_resolved, parsed

@retry(wait=wait_exponential(multiplier=2, min=15, max=70), stop=stop_after_attempt(10))
def call_gemini_rooms(client, model_name, prompt):
    return client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction="You parse hotel room names into structured JSON arrays of objects.",
            response_mime_type="application/json",
            response_schema=BatchParsedRoom,
            temperature=0.0
        )
    )

def batch_llm_parse(names, client, model_name):
    if not client:
        return [ParsedRoom(capacity=None, bed_type=None, view=None, features=[], room_class=None) for _ in names]
        
    prompt = "Parse the following list of room names into structured attributes. Preserve the order exactly.\n\n"
    for i, n in enumerate(names):
        prompt += f"{i+1}. {n}\n"
        
    try:
        response = call_gemini_rooms(client, model_name, prompt)
        response_obj = response.parsed
        if not response_obj:
            response_obj = BatchParsedRoom.model_validate_json(response.text)
        return response_obj.results
    except Exception as e:
        print(f"LLM Room Parsing Error: {e}")
        return [ParsedRoom(capacity=None, bed_type=None, view=None, features=[], room_class=None) for _ in names]

def main():
    cache_dir = "data/cache"
    config = load_config()
    
    print("--- Parsing Rooms ---")
    
    df_rooms_a = pd.read_pickle(f"{cache_dir}/rooms_a_processed.pkl")
    df_rooms_b = pd.read_pickle(f"{cache_dir}/rooms_b_processed.pkl")
    
    # Get all unique room names across both
    all_names = pd.concat([df_rooms_a['name'], df_rooms_b['name']]).dropna().unique().tolist()
    
    print(f"Total unique room names to parse: {len(all_names)}")
    
    room_cache_path = f"{cache_dir}/room_parse_cache.pkl"
    if os.path.exists(room_cache_path):
        with open(room_cache_path, "rb") as f:
            room_cache = pickle.load(f)
    else:
        room_cache = {}
        
    load_dotenv()
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY")) if os.environ.get("GEMINI_API_KEY") else None
    if not client:
        print("WARNING: GEMINI_API_KEY not set. Falling back to empty arrays for LLM step.")
        
    llm_model = config['models']['llm_model']
    
    # Process
    unresolved_names = []
    
    for name in all_names:
        if name in room_cache:
            continue
            
        # Try Smart Extractor
        is_res, parsed = smart_extract(name)
        if is_res:
            room_cache[name] = parsed
        else:
            unresolved_names.append(name)
            
    print(f"Resolved by Smart Extractor: {len(all_names) - len(unresolved_names)}")
    print(f"To be resolved by LLM: {len(unresolved_names)}")
    
    # Batch LLM
    batch_size = 20
    for i in range(0, len(unresolved_names), batch_size):
        batch = unresolved_names[i:i+batch_size]
        print(f"Processing batch {i//batch_size + 1}/{(len(unresolved_names)//batch_size)+1}...")
        results = batch_llm_parse(batch, client, llm_model)
        
        # Free-tier rate limit (15 RPM). We sleep 15s to be extremely safe.
        if client:
            time.sleep(15)
        
        # Ensure results match batch size (fallback in case of strict schema failure)
        if len(results) != len(batch):
            print(f"Warning: LLM returned {len(results)} results for batch of {len(batch)}. Falling back to empty.")
            results = [ParsedRoom(capacity=None, bed_type=None, view=None, features=[], room_class=None) for _ in batch]
            
        for name, parsed_obj in zip(batch, results):
            room_cache[name] = parsed_obj.model_dump()
            
    # Save cache
    with open(room_cache_path, "wb") as f:
        pickle.dump(room_cache, f)
        
    print("Room parsing complete. Cached.")
    
if __name__ == "__main__":
    main()

import pandas as pd
import numpy as np
import yaml
import os
import json
import re
import pickle
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

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

def regex_parse(name: str):
    name_lower = name.lower()
    parsed = {
        'capacity': None,
        'bed_type': None,
        'view': None,
        'features': set(),
        'room_class': None
    }
    
    # Simple regex rules
    if re.search(r'\b(single)\b', name_lower): parsed['capacity'] = 1
    elif re.search(r'\b(double|twin|2 adults)\b', name_lower): parsed['capacity'] = 2
    elif re.search(r'\b(triple|3 adults)\b', name_lower): parsed['capacity'] = 3
    elif re.search(r'\b(family|4 adults)\b', name_lower): parsed['capacity'] = 4
    
    if re.search(r'\b(king)\b', name_lower): parsed['bed_type'] = 'King'
    elif re.search(r'\b(queen)\b', name_lower): parsed['bed_type'] = 'Queen'
    elif re.search(r'\b(twin)\b', name_lower): parsed['bed_type'] = 'Twin'
    
    if re.search(r'\b(city view)\b', name_lower): parsed['view'] = 'City'
    elif re.search(r'\b(pool view)\b', name_lower): parsed['view'] = 'Pool'
    elif re.search(r'\b(garden view)\b', name_lower): parsed['view'] = 'Garden'
    elif re.search(r'\b(lake view)\b', name_lower): parsed['view'] = 'Lake'
    
    if re.search(r'\b(breakfast)\b', name_lower): parsed['features'].add('Breakfast')
    if re.search(r'\b(balcony)\b', name_lower): parsed['features'].add('Balcony')
    if re.search(r'\b(ac|air conditioning)\b', name_lower): parsed['features'].add('AC')
    if re.search(r'\b(wifi|wi-fi)\b', name_lower): parsed['features'].add('WiFi')
    
    if re.search(r'\b(deluxe)\b', name_lower): parsed['room_class'] = 'Deluxe'
    elif re.search(r'\b(standard)\b', name_lower): parsed['room_class'] = 'Standard'
    elif re.search(r'\b(superior)\b', name_lower): parsed['room_class'] = 'Superior'
    elif re.search(r'\b(suite)\b', name_lower): parsed['room_class'] = 'Suite'
    elif re.search(r'\b(executive)\b', name_lower): parsed['room_class'] = 'Executive'
    elif re.search(r'\b(premium)\b', name_lower): parsed['room_class'] = 'Premium'
    
    # We consider it "resolved" if we found at least a class or bed type
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
        
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY")) if os.environ.get("GEMINI_API_KEY") else None
    if not client:
        print("WARNING: GEMINI_API_KEY not set. Falling back to regex parsing exclusively for LLM step.")
        
    llm_model = config['models']['llm_model']
    
    # Process
    unresolved_names = []
    
    for name in all_names:
        if name in room_cache:
            continue
            
        # Try Regex
        is_res, parsed = regex_parse(name)
        if is_res:
            room_cache[name] = parsed
        else:
            unresolved_names.append(name)
            
    print(f"Resolved by Regex: {len(all_names) - len(unresolved_names) - len([n for n in all_names if n in room_cache])}")
    print(f"To be resolved by LLM: {len(unresolved_names)}")
    
    # Batch LLM
    batch_size = 50
    for i in range(0, len(unresolved_names), batch_size):
        batch = unresolved_names[i:i+batch_size]
        results = batch_llm_parse(batch, client, llm_model)
        
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

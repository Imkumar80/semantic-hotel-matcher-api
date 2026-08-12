import pandas as pd
import numpy as np
import re
import os
from typing import Any

def normalize_name(name: str) -> str:
    if pd.isna(name):
        return ""
    name = str(name).lower()
    name = re.sub(r'[^\w\s]', ' ', name)
    noise_tokens = [r'\bhotel\b', r'\bthe\b', r'\binn\b', r'\bresort\b', r'\bspa\b', r'\bsuites\b']
    for token in noise_tokens:
        name = re.sub(token, '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def parse_pipe_separated(val) -> list:
    if pd.isna(val) or not str(val).strip():
        return []
    items = [x.strip() for x in str(val).split('|') if x.strip()]
    seen = set()
    return [x for x in items if not (x in seen or seen.add(x))]

def extract_address_components(addr: Any):
    try:
        if pd.isna(addr) or not isinstance(addr, str):
            if not isinstance(addr, (int, float)) or pd.isna(addr):
                return "", ""
            addr = str(addr)
            
        addr = str(addr).lower()
        addr = re.sub(r'[^\w\s]', ' ', addr)
        addr = re.sub(r'\s+', ' ', addr).strip()
        
        # Try to extract numbers (often building numbers)
        numbers = " ".join(re.findall(r'\b\d+\b', addr))
        return addr, numbers
    except Exception as e:
        print(f"Warning: Failed to parse address '{addr}': {e}")
        return "", ""

def process_hotels(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    print(f"--- Processing Hotels ({source_name}) ---")
    
    df['source_dataset'] = source_name
    df['unique_id'] = df['id']  # Splink requires unique_id
    
    # Normalize names
    df['normalized_name'] = df['name'].apply(normalize_name)
    df['name_prefix'] = df['normalized_name'].str[:4]  # Used for blocking
    
    # Parse addresses
    parsed = df['address'].apply(extract_address_components)
    df['norm_addr'] = [p[0] for p in parsed]
    df['addr_numbers'] = [p[1] for p in parsed]
    
    # Amenities & Images
    if 'amenities' in df.columns:
        df['amenities_list'] = df['amenities'].apply(parse_pipe_separated)
        df['amenities_joined'] = df['amenities_list'].apply(lambda x: " ".join(x).lower())
    else:
        df['amenities_list'] = [[]] * len(df)
        df['amenities_joined'] = ""
        
    if 'image_urls' in df.columns:
        df['image_urls_list'] = df['image_urls'].apply(parse_pipe_separated)
    else:
        df['image_urls_list'] = [[]] * len(df)
    
    # Validate lat/lon
    def is_valid_coord(row):
        try:
            lat = float(row['lat'])
            lon = float(row['lon'])
            if pd.isna(lat) or pd.isna(lon):
                return False
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return False
            return True
        except (ValueError, TypeError):
            return False

    df['valid_coords'] = df.apply(is_valid_coord, axis=1)
    
    return df

def process_rooms(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    print(f"--- Processing Rooms ({source_name}) ---")
    if 'amenities' in df.columns:
        df['amenities_list'] = df['amenities'].apply(parse_pipe_separated)
    df['supplier'] = 'A' if 'A' in source_name else 'B'
    return df

def main():
    raw_dir = "data/raw"
    cache_dir = "data/cache"
    os.makedirs(cache_dir, exist_ok=True)
    
    # Process Hotels
    df_hotels_a = pd.read_csv(f"{raw_dir}/supplier_a.csv")
    df_hotels_b = pd.read_csv(f"{raw_dir}/supplier_b.csv")
    
    df_hotels_a = process_hotels(df_hotels_a, "Supplier A")
    df_hotels_b = process_hotels(df_hotels_b, "Supplier B")
    
    df_hotels_combined = pd.concat([df_hotels_a, df_hotels_b], ignore_index=True)
    
    # Process Rooms
    df_rooms_a = pd.read_csv(f"{raw_dir}/rooms_a.csv")
    df_rooms_b = pd.read_csv(f"{raw_dir}/rooms_b.csv")
    
    df_rooms_a = process_rooms(df_rooms_a, "Supplier A")
    df_rooms_b = process_rooms(df_rooms_b, "Supplier B")
    
    # Save Caches
    df_hotels_combined.to_pickle(f"{cache_dir}/hotels_combined.pkl")
    df_hotels_a.to_pickle(f"{cache_dir}/hotels_a_processed.pkl")
    df_hotels_b.to_pickle(f"{cache_dir}/hotels_b_processed.pkl")
    df_rooms_a.to_pickle(f"{cache_dir}/rooms_a_processed.pkl")
    df_rooms_b.to_pickle(f"{cache_dir}/rooms_b_processed.pkl")
    
    print(f"Preprocessing complete. Combined {len(df_hotels_combined)} hotels.")

if __name__ == "__main__":
    main()

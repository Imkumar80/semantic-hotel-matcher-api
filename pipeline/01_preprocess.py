import pandas as pd
import numpy as np
import re
import os

def normalize_name(name: str) -> str:
    if pd.isna(name):
        return ""
    # lowercase
    name = str(name).lower()
    # strip punctuation (replace with space)
    name = re.sub(r'[^\w\s]', ' ', name)
    # strip common noise tokens
    noise_tokens = [r'\bhotel\b', r'\bthe\b', r'\binn\b', r'\bresort\b', r'\bspa\b', r'\bsuites\b']
    for token in noise_tokens:
        name = re.sub(token, '', name)
    # collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def parse_pipe_separated(val) -> list:
    if pd.isna(val) or not str(val).strip():
        return []
    items = [x.strip() for x in str(val).split('|') if x.strip()]
    # dedupe while preserving order
    seen = set()
    return [x for x in items if not (x in seen or seen.add(x))]

def process_hotels(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    print(f"--- Processing Hotels ({source_name}) ---")
    print(f"Initial row count: {len(df)}")
    
    # Normalize names
    df['normalized_name'] = df['name'].apply(normalize_name)
    
    # Parse amenities and image_urls
    if 'amenities' in df.columns:
        pre_dedup_amenities_count = df['amenities'].str.split('|').apply(lambda x: len(x) if isinstance(x, list) else 0).sum()
        df['amenities_list'] = df['amenities'].apply(parse_pipe_separated)
        post_dedup_amenities_count = df['amenities_list'].apply(len).sum()
        missing_amenities = df['amenities_list'].apply(lambda x: len(x) == 0).sum()
        print(f"% missing amenities: {(missing_amenities / len(df)) * 100:.2f}%")
        print(f"Amenities deduplicated: {pre_dedup_amenities_count} -> {post_dedup_amenities_count}")

    if 'image_urls' in df.columns:
        df['image_urls_list'] = df['image_urls'].apply(parse_pipe_separated)
    
    # Validate lat/lon
    # Bangalore bounds roughly: lat 12.0 to 14.0, lon 76.0 to 79.0
    def is_valid_coord(row):
        try:
            lat = float(row['lat'])
            lon = float(row['lon'])
            if pd.isna(lat) or pd.isna(lon):
                return False
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return False
            if not (12.0 <= lat <= 14.0 and 76.0 <= lon <= 79.0):
                return False
            return True
        except (ValueError, TypeError):
            return False

    df['valid_coords'] = df.apply(is_valid_coord, axis=1)
    missing_coords = (~df['valid_coords']).sum()
    print(f"% missing/invalid coords: {(missing_coords / len(df)) * 100:.2f}%")
    
    return df

def process_rooms(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    print(f"--- Processing Rooms ({source_name}) ---")
    print(f"Initial row count: {len(df)}")
    
    if 'amenities' in df.columns:
        df['amenities_list'] = df['amenities'].apply(parse_pipe_separated)
        
    return df

def main():
    raw_dir = "data/raw"
    cache_dir = "data/cache"
    os.makedirs(cache_dir, exist_ok=True)
    
    # Load Hotels
    df_hotels_a = pd.read_csv(f"{raw_dir}/supplier_a.csv")
    df_hotels_b = pd.read_csv(f"{raw_dir}/supplier_b.csv")
    
    df_hotels_a = process_hotels(df_hotels_a, "Supplier A")
    df_hotels_b = process_hotels(df_hotels_b, "Supplier B")
    
    # Load Rooms
    df_rooms_a = pd.read_csv(f"{raw_dir}/rooms_a.csv")
    df_rooms_b = pd.read_csv(f"{raw_dir}/rooms_b.csv")
    
    df_rooms_a = process_rooms(df_rooms_a, "Supplier A")
    df_rooms_b = process_rooms(df_rooms_b, "Supplier B")
    
    # Save preprocessed data to cache
    df_hotels_a.to_pickle(f"{cache_dir}/hotels_a_processed.pkl")
    df_hotels_b.to_pickle(f"{cache_dir}/hotels_b_processed.pkl")
    df_rooms_a.to_pickle(f"{cache_dir}/rooms_a_processed.pkl")
    df_rooms_b.to_pickle(f"{cache_dir}/rooms_b_processed.pkl")
    
    print("Preprocessing complete. Data saved to data/cache/")

if __name__ == "__main__":
    main()

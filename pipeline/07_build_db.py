import json
import sqlite3
import pandas as pd
import os

def create_tables(conn):
    c = conn.cursor()
    c.executescript('''
    DROP TABLE IF EXISTS hotels;
    CREATE TABLE hotels (
        id TEXT PRIMARY KEY,
        name TEXT,
        address TEXT,
        lat REAL,
        lon REAL,
        b_lat REAL,
        b_lon REAL,
        stars TEXT,
        amenities TEXT,
        image_urls TEXT,
        confidence REAL,
        source_a_id TEXT,
        source_b_id TEXT
    );
    CREATE INDEX idx_hotels_name ON hotels(name);
    CREATE INDEX idx_hotels_lat_lon ON hotels(lat, lon);

    DROP TABLE IF EXISTS near_misses;
    CREATE TABLE near_misses (
        hotel_id TEXT,
        miss_id TEXT,
        score REAL,
        FOREIGN KEY(hotel_id) REFERENCES hotels(id)
    );

    DROP TABLE IF EXISTS rooms;
    CREATE TABLE rooms (
        room_id TEXT,
        hotel_id TEXT,
        name TEXT,
        capacity INTEGER,
        bed_type TEXT,
        view TEXT,
        meal_plan TEXT,
        features TEXT,
        room_class TEXT,
        source TEXT
    );

    DROP TABLE IF EXISTS room_matches;
    CREATE TABLE room_matches (
        hotel_a_id TEXT,
        hotel_b_id TEXT,
        room_a_id TEXT,
        room_b_id TEXT,
        score REAL
    );
    ''')
    conn.commit()

def main():
    cache_dir = "data/cache"
    canon_dir = "data/canonical"
    
    print("--- Building SQLite Database ---")
    
    # Load Canonical JSON
    with open(f"{canon_dir}/canonical_hotels.json", "r") as f:
        canonical_hotels = json.load(f)
        
    db_path = f"{canon_dir}/hotels.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn = sqlite3.connect(db_path)
    create_tables(conn)
    
    # Insert Hotels
    c = conn.cursor()
    for h in canonical_hotels:
        c.execute('''
        INSERT INTO hotels (id, name, address, lat, lon, b_lat, b_lon, stars, amenities, image_urls, confidence, source_a_id, source_b_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            h['id'], h.get('name'), h.get('address'), h.get('lat'), h.get('lon'), h.get('b_lat'), h.get('b_lon'),
            str(h.get('stars')) if h.get('stars') is not None else None,
            "|".join(h.get('amenities', [])),
            "|".join(h.get('image_urls', [])),
            h.get('confidence'), h.get('source_a_id'), h.get('source_b_id')
        ))
        
        for miss in h.get('near_miss_candidates', []):
            c.execute('INSERT INTO near_misses (hotel_id, miss_id, score) VALUES (?, ?, ?)',
                      (h['id'], miss['miss_id'], miss['score']))
                      
    conn.commit()
    
    # Insert Rooms
    if os.path.exists(f"{cache_dir}/rooms_a_processed.pkl") and os.path.exists(f"{cache_dir}/room_parse_cache.pkl"):
        df_rooms_a = pd.read_pickle(f"{cache_dir}/rooms_a_processed.pkl")
        df_rooms_b = pd.read_pickle(f"{cache_dir}/rooms_b_processed.pkl")
        
        with open(f"{cache_dir}/room_parse_cache.pkl", "rb") as f:
            room_cache = pickle.load(f)
            
        def insert_rooms(df, source):
            for _, row in df.iterrows():
                parsed = room_cache.get(row['name'], {})
                c.execute('''
                INSERT INTO rooms (room_id, hotel_id, name, capacity, bed_type, view, meal_plan, features, room_class, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row['room_id'], row['hotel_id'], row['name'],
                    parsed.get('capacity'), parsed.get('bed_type'), parsed.get('view'), parsed.get('meal_plan'),
                    "|".join(parsed.get('features', [])), parsed.get('room_class'), source
                ))
                
        insert_rooms(df_rooms_a, 'A')
        insert_rooms(df_rooms_b, 'B')
        conn.commit()
    else:
        print("Warning: Skipping room insertion because cache files are missing.")
        
    # Insert Room Matches
    if os.path.exists(f"{cache_dir}/room_matches.pkl"):
        df_room_matches = pd.read_pickle(f"{cache_dir}/room_matches.pkl")
        for _, row in df_room_matches.iterrows():
            c.execute('''
            INSERT INTO room_matches (hotel_a_id, hotel_b_id, room_a_id, room_b_id, score)
            VALUES (?, ?, ?, ?, ?)
            ''', (row['hotel_a_id'], row['hotel_b_id'], row['room_a_id'], row['room_b_id'], row['score']))
            
        conn.commit()
    else:
        print("Warning: Skipping room matches because cache file is missing.")
        
    conn.close()
    
    print(f"Database built successfully at {db_path}")

if __name__ == "__main__":
    import pickle
    main()

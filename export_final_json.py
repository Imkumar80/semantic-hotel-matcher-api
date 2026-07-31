import sqlite3
import json
import os

def export_final_artifact():
    print("Connecting to database...")
    db = sqlite3.connect('data/canonical/hotels.db')
    db.row_factory = sqlite3.Row
    c = db.cursor()

    print("Fetching hotels...")
    hotels = c.execute("SELECT * FROM hotels").fetchall()
    
    final_output = []
    
    for idx, h in enumerate(hotels):
        hotel_dict = dict(h)
        
        # Convert JSON string arrays back to actual Python lists
        for col in ['amenities', 'image_urls']:
            if hotel_dict.get(col):
                try:
                    hotel_dict[col] = json.loads(hotel_dict[col])
                except:
                    hotel_dict[col] = []
        
        source_a = h['source_a_id']
        source_b = h['source_b_id']
        matched_rooms = []
        if source_a and source_b:
            c.execute("""
                SELECT 
                    rm.score,
                    ra.room_id as a_id, ra.name as a_name, ra.capacity as a_cap, ra.bed_type as a_bed, ra.view as a_view, ra.features as a_feat, ra.room_class as a_class,
                    rb.room_id as b_id, rb.name as b_name, rb.capacity as b_cap, rb.bed_type as b_bed, rb.view as b_view, rb.features as b_feat, rb.room_class as b_class
                FROM room_matches rm
                LEFT JOIN rooms ra ON rm.room_a_id = ra.room_id
                LEFT JOIN rooms rb ON rm.room_b_id = rb.room_id
                WHERE rm.hotel_a_id = ? AND rm.hotel_b_id = ?
            """, (source_a, source_b))
            
            for rm in c.fetchall():
                matched_rooms.append({
                    "score": rm['score'],
                    "room_a": {
                        "id": rm['a_id'], "name": rm['a_name'], "capacity": rm['a_cap'], 
                        "bed_type": rm['a_bed'], "view": rm['a_view'], "room_class": rm['a_class'],
                        "features": [x for x in (rm['a_feat'] or "").split('|') if x]
                    },
                    "room_b": {
                        "id": rm['b_id'], "name": rm['b_name'], "capacity": rm['b_cap'], 
                        "bed_type": rm['b_bed'], "view": rm['b_view'], "room_class": rm['b_class'],
                        "features": [x for x in (rm['b_feat'] or "").split('|') if x]
                    }
                })
            
        hotel_dict['matched_rooms'] = matched_rooms
        final_output.append(hotel_dict)
        
        if idx % 500 == 0:
            print(f"Processed {idx}/{len(hotels)} hotels...")

    print("Writing to final_canonical_output.json...")
    with open('data/canonical/final_canonical_output.json', 'w') as f:
        json.dump(final_output, f, indent=2)
        
    print("Done! Artifact generated.")

if __name__ == "__main__":
    export_final_artifact()

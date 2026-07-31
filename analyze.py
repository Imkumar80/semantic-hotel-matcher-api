import sqlite3
import pandas as pd
import pickle

db = sqlite3.connect('data/canonical/hotels.db')
c = db.cursor()

c.execute("SELECT COUNT(*) FROM hotels")
total_canonical = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM hotels WHERE source_a_id IS NOT NULL AND source_b_id IS NOT NULL")
total_merged = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM rooms")
total_rooms = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM room_matches")
total_room_matches = c.fetchone()[0]

print(f"Total Canonical Hotels in DB (Frontend): {total_canonical}")
print(f"Total Merged Hotel Pairs: {total_merged}")
print(f"Total Raw Rooms in DB: {total_rooms}")
print(f"Total Aligned Room Pairs: {total_room_matches}")

# Let's also check the near miss scores to prove they aren't hardcoded
c.execute("SELECT score FROM near_misses LIMIT 10")
scores = c.fetchall()
print("\nSample of Near Miss Scores:")
for s in scores:
    print(f"{s[0]*100:.2f}%")

db.close()

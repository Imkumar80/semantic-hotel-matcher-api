from fastapi import FastAPI, Depends, HTTPException, Query
from typing import List
import sqlite3
from .db import get_db
from . import schemas

app = FastAPI(title="semantic-hotel-matcher-api")

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/hotels", response_model=schemas.PaginatedHotels)
def search_hotels(
    search: str = Query("", description="Search by name or address"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: sqlite3.Connection = Depends(get_db)
):
    offset = (page - 1) * size
    
    query = "SELECT * FROM hotels"
    count_query = "SELECT COUNT(*) FROM hotels"
    params = []
    
    if search:
        search_term = f"%{search}%"
        where_clause = " WHERE name LIKE ? OR address LIKE ?"
        query += where_clause
        count_query += where_clause
        params.extend([search_term, search_term])
        
    query += " LIMIT ? OFFSET ?"
    params.extend([size, offset])
    
    c = db.cursor()
    c.execute(count_query, params[:-2]) # don't include limit/offset for count
    total = c.fetchone()[0]
    
    c.execute(query, params)
    rows = c.fetchall()
    
    items = []
    for r in rows:
        items.append(schemas.CanonicalHotelSummary(
            id=r['id'],
            name=r['name'],
            address=r['address'],
            lat=r['lat'],
            lon=r['lon'],
            stars=r['stars'],
            confidence=r['confidence']
        ))
        
    return schemas.PaginatedHotels(items=items, total=total, page=page, size=size)

@app.get("/hotels/{hotel_id}", response_model=schemas.CanonicalHotelDetail)
def get_hotel(hotel_id: str, db: sqlite3.Connection = Depends(get_db)):
    c = db.cursor()
    
    # Get Hotel
    c.execute("SELECT * FROM hotels WHERE id = ?", (hotel_id,))
    row = c.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Hotel not found")
        
    # Get Near Misses
    c.execute("SELECT miss_id, score FROM near_misses WHERE hotel_id = ?", (hotel_id,))
    near_misses = [schemas.NearMiss(miss_id=m['miss_id'], score=m['score']) for m in c.fetchall()]
    
    # Get Room Matches (where this hotel is A or B)
    # Actually, if this is a merged canonical hotel, its source_a_id and source_b_id are what we look up in room_matches.
    source_a = row['source_a_id']
    source_b = row['source_b_id']
    
    matched_rooms = []
    if source_a and source_b:
        c.execute("""
            SELECT hotel_a_id, hotel_b_id, room_a_id, room_b_id, score 
            FROM room_matches 
            WHERE hotel_a_id = ? AND hotel_b_id = ?
        """, (source_a, source_b))
        
        matched_rooms = [schemas.MatchedRoom(
            hotel_a_id=rm['hotel_a_id'],
            hotel_b_id=rm['hotel_b_id'],
            room_a_id=rm['room_a_id'],
            room_b_id=rm['room_b_id'],
            score=rm['score']
        ) for rm in c.fetchall()]

    amenities = [x for x in (row['amenities'] or "").split('|') if x]
    image_urls = [x for x in (row['image_urls'] or "").split('|') if x]

    return schemas.CanonicalHotelDetail(
        id=row['id'],
        name=row['name'],
        address=row['address'],
        lat=row['lat'],
        lon=row['lon'],
        b_lat=row['b_lat'],
        b_lon=row['b_lon'],
        stars=row['stars'],
        confidence=row['confidence'],
        amenities=amenities,
        image_urls=image_urls,
        source_a_id=source_a,
        source_b_id=source_b,
        near_misses=near_misses,
        matched_rooms=matched_rooms
    )

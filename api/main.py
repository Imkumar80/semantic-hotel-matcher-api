from fastapi import BackgroundTasks, FastAPI, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import sqlite3
import os
from .db import get_db
from . import schemas
from . import projects

app = FastAPI(title="semantic-hotel-matcher-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/v1/projects", response_model=schemas.ProjectCreated, status_code=201)
def create_project(name: str | None = Query(None)):
    """Create an isolated workspace for one pair of supplier datasets."""
    return projects.create_project(name)


def require_project_key(project_id: str, x_api_key: str | None = Header(None)) -> None:
    try:
        is_valid = projects.verify_api_key(project_id, x_api_key)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    if not is_valid:
        raise HTTPException(status_code=401, detail="A valid X-API-Key header is required")


@app.post("/v1/projects/{project_id}/uploads", response_model=schemas.ProjectStatus)
async def upload_project_data(
    project_id: str,
    supplier_a_hotels: UploadFile = File(...),
    supplier_b_hotels: UploadFile = File(...),
    rooms_a: UploadFile | None = File(None),
    rooms_b: UploadFile | None = File(None),
    _: None = Depends(require_project_key),
):
    """Upload hotel CSVs and, optionally, a pair of room CSVs."""
    try:
        projects.save_upload(project_id, "supplier_a.csv", await supplier_a_hotels.read())
        projects.save_upload(project_id, "supplier_b.csv", await supplier_b_hotels.read())
        if (rooms_a is None) != (rooms_b is None):
            raise ValueError("Provide both rooms_a and rooms_b, or neither")
        if rooms_a and rooms_b:
            projects.save_upload(project_id, "rooms_a.csv", await rooms_a.read())
            projects.save_upload(project_id, "rooms_b.csv", await rooms_b.read())
        return projects.write_status(project_id, status="uploaded", progress=0, stage="ready to run")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.post("/v1/projects/{project_id}/runs", response_model=schemas.ProjectStatus, status_code=202)
def start_project_run(project_id: str, background_tasks: BackgroundTasks, _: None = Depends(require_project_key)):
    """Start matching uploaded records without blocking the HTTP request."""
    try:
        status = projects.read_status(project_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    if status["status"] == "running":
        raise HTTPException(status_code=409, detail="A pipeline run is already in progress")
    raw_dir = projects.project_path(project_id) / "raw"
    if not (raw_dir / "supplier_a.csv").exists() or not (raw_dir / "supplier_b.csv").exists():
        raise HTTPException(status_code=409, detail="Upload both supplier hotel CSVs before starting a run")
    status = projects.write_status(project_id, status="queued", progress=0, stage="queued", error=None)
    background_tasks.add_task(projects.run_project, project_id)
    return status


@app.get("/v1/projects/{project_id}", response_model=schemas.ProjectStatus)
def get_project_status(project_id: str, _: None = Depends(require_project_key)):
    try:
        return projects.read_status(project_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


def get_project_db(project_id: str):
    try:
        db_path = projects.project_path(project_id) / "hotels.db"
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    if not db_path.exists():
        raise HTTPException(status_code=409, detail="Results are not ready; check the project status")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@app.get("/v1/projects/{project_id}/hotels", response_model=schemas.PaginatedHotels)
def search_project_hotels(
    project_id: str,
    search: str = Query("", description="Search by name or address"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: None = Depends(require_project_key),
    db: sqlite3.Connection = Depends(get_project_db),
):
    offset = (page - 1) * size
    params: list[object] = []
    where = ""
    if search:
        where = " WHERE name LIKE ? OR address LIKE ?"
        params = [f"%{search}%", f"%{search}%"]
    total = db.execute("SELECT COUNT(*) FROM hotels" + where, params).fetchone()[0]
    rows = db.execute("SELECT * FROM hotels" + where + " LIMIT ? OFFSET ?", params + [size, offset]).fetchall()
    items = [schemas.CanonicalHotelSummary(
        id=row["id"], name=row["name"], address=row["address"], lat=row["lat"], lon=row["lon"],
        stars=row["stars"], confidence=row["confidence"],
    ) for row in rows]
    return schemas.PaginatedHotels(items=items, total=total, page=page, size=size)


@app.get("/v1/projects/{project_id}/hotels/{hotel_id}/room-matches", response_model=List[schemas.MatchedRoom])
def project_room_matches(
    project_id: str,
    hotel_id: str,
    _: None = Depends(require_project_key),
    db: sqlite3.Connection = Depends(get_project_db),
):
    hotel = db.execute("SELECT source_a_id, source_b_id FROM hotels WHERE id = ?", (hotel_id,)).fetchone()
    if not hotel:
        raise HTTPException(status_code=404, detail="Hotel not found")
    if not hotel["source_a_id"] or not hotel["source_b_id"]:
        return []
    rows = db.execute("""
        SELECT rm.score, ra.room_id AS a_id, ra.name AS a_name, rb.room_id AS b_id, rb.name AS b_name
        FROM room_matches rm
        JOIN rooms ra ON ra.room_id = rm.room_a_id
        JOIN rooms rb ON rb.room_id = rm.room_b_id
        WHERE rm.hotel_a_id = ? AND rm.hotel_b_id = ?
    """, (hotel["source_a_id"], hotel["source_b_id"])).fetchall()
    return [schemas.MatchedRoom(
        score=row["score"],
        room_a=schemas.RoomDetail(id=row["a_id"], name=row["a_name"], capacity=None, bed_type=None, view=None, meal_plan=None, features=[], room_class=None),
        room_b=schemas.RoomDetail(id=row["b_id"], name=row["b_name"], capacity=None, bed_type=None, view=None, meal_plan=None, features=[], room_class=None),
    ) for row in rows]

@app.get("/hotels", response_model=schemas.PaginatedHotels)
def search_hotels(
    search: str = Query("", description="Search by name or address"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1),
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
    
    a_ids = source_a.split(',') if source_a else []
    b_ids = source_b.split(',') if source_b else []
    
    if a_ids and b_ids:
        placeholders_a = ','.join('?' * len(a_ids))
        placeholders_b = ','.join('?' * len(b_ids))
        
        matched_a_ids = set()
        matched_b_ids = set()
        
        # 1. Get Matched Rooms
        c.execute(f"""
            SELECT 
                rm.score,
                ra.room_id as a_id, ra.name as a_name, ra.capacity as a_cap, ra.bed_type as a_bed, ra.view as a_view, ra.meal_plan as a_meal, ra.features as a_feat, ra.room_class as a_class,
                rb.room_id as b_id, rb.name as b_name, rb.capacity as b_cap, rb.bed_type as b_bed, rb.view as b_view, rb.meal_plan as b_meal, rb.features as b_feat, rb.room_class as b_class
            FROM room_matches rm
            LEFT JOIN rooms ra ON rm.room_a_id = ra.room_id
            LEFT JOIN rooms rb ON rm.room_b_id = rb.room_id
            WHERE rm.hotel_a_id IN ({placeholders_a}) AND rm.hotel_b_id IN ({placeholders_b})
        """, tuple(a_ids + b_ids))
        
        for rm in c.fetchall():
            matched_a_ids.add(rm['a_id'])
            matched_b_ids.add(rm['b_id'])
            room_a = schemas.RoomDetail(
                id=rm['a_id'], name=rm['a_name'], capacity=rm['a_cap'], bed_type=rm['a_bed'], view=rm['a_view'], meal_plan=rm['a_meal'],
                features=[x for x in (rm['a_feat'] or "").split('|') if x], room_class=rm['a_class']
            )
            room_b = schemas.RoomDetail(
                id=rm['b_id'], name=rm['b_name'], capacity=rm['b_cap'], bed_type=rm['b_bed'], view=rm['b_view'], meal_plan=rm['b_meal'],
                features=[x for x in (rm['b_feat'] or "").split('|') if x], room_class=rm['b_class']
            )
            matched_rooms.append(schemas.MatchedRoom(score=rm['score'], room_a=room_a, room_b=room_b))
            
        # 2. Get Unmatched A Rooms
        c.execute(f"SELECT * FROM rooms WHERE hotel_id IN ({placeholders_a})", tuple(a_ids))
        for ra in c.fetchall():
            if ra['room_id'] not in matched_a_ids:
                room_a = schemas.RoomDetail(
                    id=ra['room_id'], name=ra['name'], capacity=ra['capacity'], bed_type=ra['bed_type'], view=ra['view'], meal_plan=ra['meal_plan'],
                    features=[x for x in (ra['features'] or "").split('|') if x], room_class=ra['room_class']
                )
                matched_rooms.append(schemas.MatchedRoom(score=0.0, room_a=room_a, room_b=None))
                
        # 3. Get Unmatched B Rooms
        c.execute(f"SELECT * FROM rooms WHERE hotel_id IN ({placeholders_b})", tuple(b_ids))
        for rb in c.fetchall():
            if rb['room_id'] not in matched_b_ids:
                room_b = schemas.RoomDetail(
                    id=rb['room_id'], name=rb['name'], capacity=rb['capacity'], bed_type=rb['bed_type'], view=rb['view'], meal_plan=rb['meal_plan'],
                    features=[x for x in (rb['features'] or "").split('|') if x], room_class=rb['room_class']
                )
                matched_rooms.append(schemas.MatchedRoom(score=0.0, room_a=None, room_b=room_b))
            
    elif a_ids:
        placeholders_a = ','.join('?' * len(a_ids))
        c.execute(f"SELECT * FROM rooms WHERE hotel_id IN ({placeholders_a})", tuple(a_ids))
        for ra in c.fetchall():
            room_a = schemas.RoomDetail(
                id=ra['room_id'], name=ra['name'], capacity=ra['capacity'], bed_type=ra['bed_type'], view=ra['view'], meal_plan=ra['meal_plan'],
                features=[x for x in (ra['features'] or "").split('|') if x], room_class=ra['room_class']
            )
            matched_rooms.append(schemas.MatchedRoom(score=0.0, room_a=room_a, room_b=None))
            
    elif b_ids:
        placeholders_b = ','.join('?' * len(b_ids))
        c.execute(f"SELECT * FROM rooms WHERE hotel_id IN ({placeholders_b})", tuple(b_ids))
        for rb in c.fetchall():
            room_b = schemas.RoomDetail(
                id=rb['room_id'], name=rb['name'], capacity=rb['capacity'], bed_type=rb['bed_type'], view=rb['view'], meal_plan=rb['meal_plan'],
                features=[x for x in (rb['features'] or "").split('|') if x], room_class=rb['room_class']
            )
            matched_rooms.append(schemas.MatchedRoom(score=0.0, room_a=None, room_b=room_b))

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

# Mount UI last so it doesn't override API routes
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

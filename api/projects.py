"""Per-project storage and a lightweight, deterministic matching job.

The original pipeline is intentionally batch-oriented.  This module provides
an isolated API-friendly execution path: every project owns its uploaded data,
status and SQLite result database.  It does not mutate the demo database.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import math
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rapidfuzz.fuzz import token_set_ratio

PROJECTS_DIR = Path("data/projects")
REQUIRED_HOTEL_COLUMNS = {"id", "name", "address", "lat", "lon"}
REQUIRED_ROOM_COLUMNS = {"room_id", "hotel_id", "name"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_path(project_id: str) -> Path:
    # UUID validation also prevents path traversal.
    uuid.UUID(project_id)
    return PROJECTS_DIR / project_id


def status_path(project_id: str) -> Path:
    return project_path(project_id) / "status.json"


def read_status(project_id: str) -> dict[str, Any]:
    path = status_path(project_id)
    if not path.exists():
        raise FileNotFoundError(project_id)
    return json.loads(path.read_text(encoding="utf-8"))


def write_status(project_id: str, **values: Any) -> dict[str, Any]:
    current = read_status(project_id)
    current.update(values)
    current["updated_at"] = utc_now()
    status_path(project_id).write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def create_project(name: str | None) -> dict[str, Any]:
    project_id = str(uuid.uuid4())
    directory = project_path(project_id)
    (directory / "raw").mkdir(parents=True)
    api_key = f"shm_{secrets.token_urlsafe(32)}"
    status = {
        "project_id": project_id,
        "name": name or "Untitled project",
        "status": "created",
        "progress": 0,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "api_key_hash": hashlib.sha256(api_key.encode()).hexdigest(),
    }
    status_path(project_id).write_text(json.dumps(status, indent=2), encoding="utf-8")
    # The key is returned once; only its hash is retained on disk.
    return {**status, "api_key": api_key}


def verify_api_key(project_id: str, api_key: str | None) -> bool:
    if not api_key:
        return False
    expected = read_status(project_id).get("api_key_hash", "")
    supplied = hashlib.sha256(api_key.encode()).hexdigest()
    return hmac.compare_digest(expected, supplied)


def save_upload(project_id: str, filename: str, content: bytes) -> None:
    if not content:
        raise ValueError(f"{filename} is empty")
    if len(content) > 50 * 1024 * 1024:
        raise ValueError(f"{filename} exceeds the 50 MB upload limit")
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{filename} must be UTF-8 encoded") from exc
    (project_path(project_id) / "raw" / filename).write_bytes(content)


def load_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        missing = sorted(required - columns)
        if missing:
            raise ValueError(f"{path.name} is missing required columns: {', '.join(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path.name} has no data rows")
    return rows


def text(value: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(value or "").lower()).strip()


def number(value: Any) -> float | None:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def similarity(left: dict[str, str], right: dict[str, str]) -> float:
    name = token_set_ratio(text(left["name"]), text(right["name"])) / 100
    address = token_set_ratio(text(left["address"]), text(right["address"])) / 100
    score = 0.75 * name + 0.25 * address
    left_lat, left_lon = number(left["lat"]), number(left["lon"])
    right_lat, right_lon = number(right["lat"]), number(right["lon"])
    if None not in (left_lat, left_lon, right_lat, right_lon):
        distance = math.hypot(left_lat - right_lat, left_lon - right_lon)
        if distance < 0.01:
            score = min(1.0, score + 0.1)
    return round(score, 4)


def initialise_database(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE hotels (
          id TEXT PRIMARY KEY, name TEXT, address TEXT, lat REAL, lon REAL,
          b_lat REAL, b_lon REAL, stars TEXT, amenities TEXT, image_urls TEXT,
          confidence REAL, source_a_id TEXT, source_b_id TEXT
        );
        CREATE INDEX idx_hotels_name ON hotels(name);
        CREATE TABLE near_misses (hotel_id TEXT, miss_id TEXT, score REAL);
        CREATE TABLE rooms (
          room_id TEXT, hotel_id TEXT, name TEXT, capacity INTEGER, bed_type TEXT,
          view TEXT, meal_plan TEXT, features TEXT, room_class TEXT, source TEXT
        );
        CREATE TABLE room_matches (
          hotel_a_id TEXT, hotel_b_id TEXT, room_a_id TEXT, room_b_id TEXT, score REAL
        );
    """)
    return connection


def room_score(room_a: dict[str, str], room_b: dict[str, str]) -> float:
    return round(token_set_ratio(text(room_a["name"]), text(room_b["name"])) / 100, 4)


def insert_room(conn: sqlite3.Connection, room: dict[str, str], source: str) -> None:
    conn.execute("INSERT INTO rooms VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
        room["room_id"], room["hotel_id"], room["name"], number(room.get("capacity")),
        room.get("bed_type"), room.get("view"), room.get("meal_plan"), room.get("features", ""),
        room.get("room_class"), source,
    ))


def run_project(project_id: str) -> None:
    """Build a project-local canonical database using the generic EntityMatcher."""
    try:
        import pandas as pd
        from src.semantic_entity_matcher.core.matcher import EntityMatcher
        from src.semantic_entity_matcher.core.config import MatcherConfig
        
        directory = project_path(project_id)
        raw = directory / "raw"
        write_status(project_id, status="running", progress=10, stage="validating uploads")
        
        # In a fully dynamic API, the config would be uploaded by the user.
        # For now, we construct a default hotel-like config to maintain compatibility.
        config_dict = {
            "entity_type": "hotels",
            "id_column": "id",
            "match_columns": {
                "name": {"type": "text", "normalizer": "text_normalizer"},
                "address": {"type": "text", "normalizer": "address_normalizer"},
                "lat": {"type": "location", "normalizer": "numeric_normalizer"},
                "lon": {"type": "location", "normalizer": "numeric_normalizer"},
            },
            "strategy": "splink",
            "matching": {"auto_match_threshold": 0.84, "min_score_threshold": 0.20},
            "output": {"format": "sqlite", "include_near_misses": True}
        }
        config = MatcherConfig(**config_dict)
        
        write_status(project_id, progress=35, stage="matching entities")
        
        matcher = EntityMatcher(verbose=False)
        results = matcher.match(
            left=str(raw / "supplier_a.csv"),
            right=str(raw / "supplier_b.csv"),
            config=config,
            output_dir=str(directory)
        )
        
        # EntityMatcher creates the SQLite DB automatically at directory/hotels.db
        db_path = directory / "hotels.db"
        
        # We still need to process rooms if they were uploaded.
        rooms_a_path, rooms_b_path = raw / "rooms_a.csv", raw / "rooms_b.csv"
        if rooms_a_path.exists() and rooms_b_path.exists():
            write_status(project_id, progress=70, stage="matching rooms")
            rooms_a = load_csv(rooms_a_path, REQUIRED_ROOM_COLUMNS)
            rooms_b = load_csv(rooms_b_path, REQUIRED_ROOM_COLUMNS)
            
            # Reopen the generic DB to append rooms
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            
            # We need to recreate the rooms tables
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS rooms (
                  room_id TEXT, hotel_id TEXT, name TEXT, capacity INTEGER, bed_type TEXT,
                  view TEXT, meal_plan TEXT, features TEXT, room_class TEXT, source TEXT
                );
                CREATE TABLE IF NOT EXISTS room_matches (
                  hotel_a_id TEXT, hotel_b_id TEXT, room_a_id TEXT, room_b_id TEXT, score REAL
                );
            """)
            
            for room in rooms_a:
                insert_room(conn, room, "A")
            for room in rooms_b:
                insert_room(conn, room, "B")
                
            # Perform simple room matching on matched hotels
            canonical = results["canonical"]
            matched_hotels = [(h, h) for h in canonical if h.get("source_left_id") and h.get("source_right_id")]
            
            rooms_by_a = {}
            rooms_by_b = {}
            for room in rooms_a: rooms_by_a.setdefault(room["hotel_id"], []).append(room)
            for room in rooms_b: rooms_by_b.setdefault(room["hotel_id"], []).append(room)
                
            for h_a, h_b in matched_hotels:
                a_id = h_a["source_left_id"]
                b_id = h_b["source_right_id"]
                
                candidates = sorted(
                    ((room_score(a, b), a, b) for a in rooms_by_a.get(a_id, []) for b in rooms_by_b.get(b_id, [])),
                    reverse=True, key=lambda row: row[0],
                )
                used_a, used_b = set(), set()
                for score, room_a, room_b in candidates:
                    if score < 0.65 or room_a["room_id"] in used_a or room_b["room_id"] in used_b: continue
                    used_a.add(room_a["room_id"])
                    used_b.add(room_b["room_id"])
                    conn.execute("INSERT INTO room_matches VALUES (?, ?, ?, ?, ?)", (
                        a_id, b_id, room_a["room_id"], room_b["room_id"], score,
                    ))
            conn.commit()
            conn.close()
            room_count = len(rooms_a) + len(rooms_b)
        else:
            room_count = 0
            
        # The generic matcher creates 'entities' table, but API expects 'hotels'. Let's rename it.
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("ALTER TABLE entities RENAME TO hotels")
        except sqlite3.OperationalError:
            pass # already renamed or doesn't exist
            
        # Ensure required columns for the API exist, since generic matcher might omit them if not in CSV
        try:
            conn.execute("ALTER TABLE hotels ADD COLUMN source_a_id TEXT")
            conn.execute("ALTER TABLE hotels ADD COLUMN source_b_id TEXT")
        except sqlite3.OperationalError:
            pass
        
        # Populate source_a_id and source_b_id for API compatibility
        conn.execute("UPDATE hotels SET source_a_id = source_left_id, source_b_id = source_right_id")
        conn.commit()
        conn.close()

        write_status(project_id, status="completed", progress=100, stage="completed", hotel_count=len(results["canonical"]), room_count=room_count)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        write_status(project_id, status="failed", progress=100, stage="failed", error=str(exc))

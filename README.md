# Semantic Hotel Matcher API

A high-performance pipeline and API for resolving disjoint, messy hotel supplier data into a pristine canonical schema.

## 🏗️ System Architecture

```mermaid
graph TD
    A[Raw Data CSVs] --> B(01_clean_data.py)
    B -->|Normalized Text| C(02_splink_match.py)
    C -->|Probabilistic Matches| D(03_resolve_hotels.py)
    D -->|Canonical Hotels| E(04_embed_rooms.py)
    E --> F(05_parse_rooms.py - Smart Extractor)
    F -->|Parsed Capacity/Beds| G(06_match_rooms.py)
    G -->|Room Inventory| H(07_build_db.py)
    H -->|SQLite Database| I[FastAPI Backend]
    I -->|JSON / OpenAPI| J[React Frontend]
```
## 🚀 Quick Start 

The entire pipeline and API are fully dockerized. To build the SQLite database and start the web server in one command:

```bash
docker compose up --build
```
*(Note: If you want to rebuild the database from scratch and hit the LLM/Embeddings, provide a `.env` with `GEMINI_API_KEY` and run `uv run pipeline/run_all.py` first).*

Once running, **open your browser to [http://localhost:8000](http://localhost:8000)** to view the beautiful interactive UI!

## 📡 API Contract & OpenAPI Sketch

FastAPI automatically generates a Swagger UI. You can view the full interactive OpenAPI schema at:
👉 **[http://localhost:8000/docs](http://localhost:8000/docs)**

### Example Requests

**1. Search Hotels**
```bash
curl "http://localhost:8000/hotels?search=Hilton&size=5"
```
*Returns a paginated list of canonical hotels matching the query.*

**2. Get Canonical Hotel Details**
```bash
curl "http://localhost:8000/hotels/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
```
*Returns the deeply nested canonical record. A frontend could easily build a complete hotel page using just this one response.*

### The `/hotels/{id}` Response Payload
```json
{
  "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "name": "Hilton Bengaluru Embassy GolfLinks",
  "address": "Embassy GolfLinks Business Park, Off Intermediate Ring Road, Bangalore",
  "lat": 12.9567,
  "lon": 77.6412,
  "stars": 5.0,
  "confidence": 0.98,
  "amenities": ["WiFi", "Pool", "Gym", "Spa"],
  "image_urls": ["https://cdn.example.com/img1.jpg"],
  "source_a_id": "A-12345",
  "source_b_id": "B-98765",
  "near_misses": [
    {
      "miss_id": "B-11223",
      "score": 0.82
    }
  ],
  "matched_rooms": [
    {
      "score": 0.96,
      "room_a": {
        "id": "A-RM-001",
        "name": "Deluxe King Room",
        "capacity": 2,
        "bed_type": "King",
        "view": "City",
        "features": ["Air Conditioning", "Bathtub", "Mini-bar"],
        "room_class": "Deluxe"
      },
      "room_b": {
        "id": "B-RM-001",
        "name": "King Deluxe - City View",
        "capacity": 2,
        "bed_type": "King",
        "view": "City",
        "features": ["Air Conditioning", "Bathtub"],
        "room_class": "Deluxe"
      }
    }
  ]
}
```


# Semantic Hotel Matcher API

This repository implements the 8-stage data pipeline for Semantic Hotel Entity Resolution, transforming disjoint, dirty CSV files into a fast, queryable SQLite canonical database. It also provides a lightweight, performant FastAPI endpoint to query the canonicalized hotels.

## Architecture and Approach

### Data Pipeline
The entity resolution pipeline is broken into 8 distinct scripts that can be executed end-to-end via `uv run pipeline/run_all.py`:
1. **Preprocess (`01_preprocess.py`)**: Normalizes case, tokenizes strings, maps amenities to a standard vocabulary, and rejects missing coordinates.
2. **Candidates (`02_candidates.py`)**: Sub-selects potential hotel pairs using a spatial `BallTree` on coordinates (0.2km radius) as the primary index, with a `RapidFuzz` string similarity fallback for bad coords.
3. **Score (`03_score_hotels.py`)**: Calculates a weighted score using heuristics (name fuzzy match, address missing-token, Haversine distance, amenity Jaccard) and semantic similarity using `BAAI/bge-small-en-v1.5` embeddings. Embeddings are aggressively cached.
4. **Resolve (`04_resolve_hotels.py`)**: Applies decision bands to matches. Near-certain matches are auto-accepted. Borderline cases are optionally routed to `gpt-4o-mini` for strict JSON verification (fallback to rejection if API limit is hit or no key).
5. **Merge (`05_merge_hotels.py`)**: Constructs Canonical properties using predefined rules (longest name, union of amenities, A's coordinates).
6. **Parse Rooms (`06_parse_rooms.py`)**: Extracts structured dimensions (capacity, bed type, view, class) from raw room strings using deterministic regex rules, batching unresolved cases to the LLM.
7. **Match Rooms (`07_match_rooms.py`)**: Maps rooms between matched hotels using Jaccard similarity and exact matching heuristics.
8. **Build DB (`08_build_db.py`)**: Commits everything into a relational SQLite database schema.

### API Server
A lightweight API built with FastAPI that reads directly from `data/canonical/hotels.db`:
- `GET /hotels`: Paginated, indexed text search.
- `GET /hotels/{id}`: Full nested record including canonical details, near-misses, and matched rooms.

The API requires absolutely no external dependencies at runtime.

## Running the Project
```bash
# Build the DB
uv run pipeline/run_all.py

# Start API via Docker
docker-compose up --build
```

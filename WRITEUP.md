# Semantic Hotel Matcher API

This repository implements the 8-stage data pipeline for Semantic Hotel Entity Resolution, transforming disjoint, dirty CSV files into a fast, queryable SQLite canonical database. It also provides a lightweight, performant FastAPI endpoint to query the canonicalized hotels.

## Architecture and Approach

### Data Pipeline
The entity resolution pipeline is broken into 8 distinct scripts that can be executed end-to-end via `uv run pipeline/run_all.py`:
1. **Preprocess (`01_preprocess.py`)**: Normalizes case, tokenizes strings, maps amenities to a standard vocabulary, and rejects missing coordinates.
2. **Candidates (`02_candidates.py`)**: Sub-selects potential hotel pairs using a spatial `BallTree` on coordinates (0.2km radius) as the primary index, with a `RapidFuzz` string similarity fallback for bad coords.
3. **Score (`03_score_hotels.py`)**: Calculates a weighted score using heuristics (name fuzzy match, address missing-token, Haversine distance, amenity Jaccard) and semantic similarity using `BAAI/bge-small-en-v1.5` embeddings. Embeddings are aggressively cached.
4. **Resolve (`04_resolve_hotels.py`)**: Applies decision bands to matches. Near-certain matches (>0.92) are auto-accepted. I explored replacing the LLM with a pseudo-labeled Random Forest trained on high-confidence heuristic matches. While this eliminated inference cost and executed in under a minute, the model was trained on labels derived from the same similarity features used by the heuristic. As a result, it provided limited independent evidence on ambiguous cases. I therefore retained the heuristic scorer as the primary signal and used an LLM (optionally augmented with OpenStreetMap context) only for a small set of genuinely ambiguous matches. By analyzing the heuristic score distribution, I determined that a threshold of 0.84 empirically isolated exactly 98 ambiguous pairs requiring LLM review. This data-driven calibration ensured we only sent the most difficult cases to the LLM, where semantic reasoning and external geographic knowledge provide complementary information.
5. **Merge (`05_merge_hotels.py`)**: Constructs Canonical properties using predefined rules (longest name, union of amenities, A's coordinates).
6. **Parse Rooms (`06_parse_rooms.py`)**: Extracts structured dimensions (capacity, bed type, view, class) from raw room strings using deterministic regex rules, batching unresolved cases to the LLM.
7. **Match Rooms (`07_match_rooms.py`)**: Maps rooms between matched hotels using Jaccard similarity and exact matching heuristics.
8. **Build DB (`08_build_db.py`)**: Commits everything into a relational SQLite database schema.

### API Server
A lightweight API built with FastAPI that reads directly from `data/canonical/hotels.db`:
- `GET /hotels`: Paginated, indexed text search.
- `GET /hotels/{id}`: Full nested record including canonical details, near-misses, and matched rooms.

The API requires absolutely no external dependencies at runtime.

### Alternatives Considered
| Approach | Decision |
| -------- | -------- |
| Pure fuzzy matching | Too brittle on foreign vocabularies |
| Embeddings only | Misses geographic context entirely |
| Random Forest pseudo-labeling | Explored, not adopted (heuristic correlation) |
| LLM on all pairs | Too expensive / impossible at scale |
| Selective LLM with OSM | **Final choice ✅** |

## Running the Project
```bash
# Build the DB
uv run pipeline/run_all.py

# Start API via Docker
docker-compose up --build
```

## Scaling to 200,000 Hotels
**"What breaks first at 200,000 hotels across 3 suppliers?"**

If we were using an LLM to resolve all borderline matches blindly, the system would immediately break on API rate limits and token costs. 200,000 hotels would generate tens of thousands of candidates, translating to thousands of dollars in API spend and days of execution time due to rate limits (like Gemini's 15 RPM). 

To scale this, we rely on the empirical data-driven thresholds calibrated in step 4. By aggressively auto-matching and auto-rejecting 99% of pairs via fast $O(1)$ heuristic scoring, we strict-bound the LLM queue to a tiny, constant-sized subset of edge cases regardless of the total market size, keeping API costs near zero.

At 200,000 hotels, what breaks next is the spatial join in step 2 (`02_candidates.py`). Currently, a `BallTree` on coordinates handles thousands of hotels instantly, but as density increases, a simple radius query will return too many candidates. The fallback string similarity candidate generator (`RapidFuzz`) will also degrade from $O(N^2)$ cross-matching. To fix this, we would introduce a distributed inverted index (like Elasticsearch) or blocking techniques (e.g., MinHash LSH) to generate match candidates.

## What Was Cut For Time
If I had another week to build this pipeline for production, I would add:
1. **Airflow / Prefect Orchestration:** The pipeline currently runs linearly via a python wrapper script. In production, steps like Embedding generation and Candidate scoring should be parallelized across distributed workers using a proper orchestrator.
2. **Proper LLM Evaluation Set:** I would manually label ~500 ambiguous pairs to create a ground-truth evaluation set. This would allow us to programmatically measure the precision/recall of Gemini's outputs when we tweak prompts, rather than just eyeballing the `near_misses` dictionary.
3. **Automated Data Quality Alerts:** Before step 1, I would run `Great Expectations` to catch schema drifts (e.g., if a supplier suddenly renames `latitude` to `lat` or starts returning nulls for 90% of rows).

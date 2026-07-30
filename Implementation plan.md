# Away Hotels Layer — Implementation Plan

## Repo structure
```text
away-hotels/
├── pipeline/
│   ├── 01_preprocess.py        # load, clean, normalize CSVs
│   ├── 02_candidates.py        # blocking → candidate pairs
│   ├── 03_score_hotels.py      # heuristics + embeddings → scores
│   ├── 04_resolve_hotels.py    # decision bands, LLM verification, near-misses
│   ├── 05_merge_hotels.py      # build canonical hotel records
│   ├── 06_parse_rooms.py       # room name → structured attributes (LLM)
│   ├── 07_match_rooms.py       # align rooms within matched hotels
│   └── 08_build_db.py          # write everything to SQLite
├── api/
│   ├── main.py                 # FastAPI app
│   ├── db.py                   # SQLite access layer
│   └── schemas.py              # Pydantic response models
├── config/
│   └── config.yaml             # all thresholds, radii, weights, model names
├── data/
│   ├── raw/                    # input CSVs (gitignored except maybe sample)
│   ├── cache/                  # LLM responses, embeddings — committed
│   └── canonical/              # final canonical_hotels.json/sqlite — committed
├── tests/
│   ├── test_scoring.py
│   ├── test_room_matching.py
│   └── test_api.py
├── docker-compose.yml
├── Dockerfile
├── README.md
└── WRITEUP.md
```

Run everything with `uv run pipeline/run_all.py` (or a Makefile target) that calls stages 01–08 in order, then `docker compose up` starts the API off the committed SQLite file. Reviewer should never need your API keys to run the API — only to regenerate the pipeline, and even then the cache should make re-runs mostly free.

## `config/config.yaml`
```yaml
matching:
  auto_match_threshold: 0.92
  llm_review_threshold: 0.75      # below this = no match, no LLM call
  radius_meters: 250
  max_candidates_per_hotel: 10

weights:
  name: 0.30
  embedding: 0.25
  address: 0.20
  distance: 0.15
  amenities: 0.10

rooms:
  match_threshold: 0.65

models:
  embedding_model: "BAAI/bge-small-en-v1.5"
  llm_model: "gpt-4o-mini"        # or your OpenRouter pick — confirm provider first
```
Nothing in the pipeline hardcodes a number that appears here — every threshold traces back to this file, so "why 250m?" has a real answer: it's tuned against the validation sample, documented in the write-up.

## Pipeline Stages

**Stage 1 — Preprocess (`01_preprocess.py`)**
Load both hotel CSVs and both room CSVs with pandas.
Normalize names: lowercase, strip punctuation, collapse whitespace, strip common noise tokens ("Hotel", "The", "Inn") into a separate normalized field — keep the original for display.
Parse amenities and image_urls (pipe-split), drop empties, dedupe within a row.
Validate lat/lon ranges; flag rows with missing/out-of-range coords for name-only fallback blocking later.
Log: row counts, % missing coords, % missing amenities, before/after dedup counts.

**Stage 2 — Candidate generation (`02_candidates.py`)**
Build a KDTree (or geohash grid) over Supplier B coordinates.
For each Supplier A hotel with valid coords: query all B hotels within radius_meters.
For A hotels with missing/bad coords: fallback to top-K RapidFuzz matches on normalized name across all of B (bounded, e.g. top 20).
Output: (a_id, b_id) candidate pairs — expect this to collapse ~13M → low tens of thousands.
Log: candidate count, avg candidates/hotel, count of name-fallback hotels.

**Stage 3 — Score hotels (`03_score_hotels.py`)**
For every candidate pair compute:
- Name score: RapidFuzz token-sort ratio on normalized names, scaled 0–1.
- Embedding score: cosine similarity of bge-small-en-v1.5 embeddings over name+address string. Batch-embed all unique hotel strings once (not per-pair) and cache.
- Address score: token-set overlap (Jaccard or RapidFuzz) on normalized address.
- Distance score: 1 - min(haversine_m / radius_meters, 1).
- Amenity score: Jaccard overlap after mapping both sides' amenities to a small canonical vocabulary (hand-built synonym dict + RapidFuzz fallback for unmapped terms).
Combine via the weights in config → final_score. Store all component scores, not just the final one — needed for both the near-miss explanation and the debrief.

**Stage 4 — Resolve hotels (`04_resolve_hotels.py`)**
Three bands, per config:
1. `score >= auto_match_threshold` → MATCH, no LLM call.
2. `llm_review_threshold <= score < auto_match_threshold` → LLM verification. Send both records (name, address, coords, stars) with a constrained prompt requiring strict JSON: `{"is_match": bool, "confidence": float, "reason": str}`. Cache every response keyed by `(a_id, b_id)` so re-runs cost nothing.
3. `score < llm_review_threshold` → NO MATCH.
Final hotel confidence: if LLM was called, blend rather than override — e.g. `0.5 * heuristic_score + 0.5 * llm_confidence` — so a strong heuristic signal isn't discarded on a single LLM call. Document this blend explicitly in the write-up as a deliberate choice.
For every A hotel, keep the best rejected/borderline B candidate (and vice versa where relevant) as a near-miss, with its score breakdown, even if a match was found — this is what `/hotels/{id}` needs to expose.
Log: match/no-match/LLM-reviewed counts, LLM $ spend running total, avg LLM confidence.

**Stage 5 — Merge hotels (`05_merge_hotels.py`)**
For each matched pair, build the canonical record:
- Name: longer of the two (or the one with higher individual name-quality heuristic — pick one rule, state it).
- Address: prefer the more complete string (fewer missing tokens).
- Coordinates: prefer Supplier A's coordinates as the primary, store B's alongside (do not average).
- Stars: prefer non-null; if both present and disagree, keep both and flag conflict.
- Amenities: union after canonical-vocabulary mapping.
- Images: concatenate, dedupe by URL.
Always retain: `source_a_id`, `source_b_id`, `hotel_confidence`, `near_miss_candidates[]`.
Unmatched hotels on either side become their own canonical entries with a single source and confidence: null (or 1.0 for "no ambiguity, single source" — pick one and state it).

**Stage 6 — Room attribute extraction (`06_parse_rooms.py`)**
Dedupe unique room names across both rooms CSVs (expect big reduction — many rooms share names within/across hotels).
Try deterministic regex/rule parsing first for common patterns (bed type keywords, "w/ Breakfast", view keywords) — this alone should resolve a solid fraction.
Batch remaining unresolved names (~50/prompt) through the LLM with structured output:
```json
{"capacity": 2, "bed_type": "Twin", "view": "City", "features": ["Breakfast", "Balcony"], "class": "Deluxe"}
```
Cache by room-name string so the LLM never sees the same string twice.
Log: % resolved by rules vs LLM, total room-parsing $ spend.

**Stage 7 — Match rooms (`07_match_rooms.py`)**
Only runs for hotels with a confirmed match.
Compute room similarity: `0.4 * exact_bed_match + 0.3 * capacity_match + 0.3 * jaccard(features ∪ class)`.
Greedy one-to-many matching above `rooms.match_threshold` (documented trade-off: a coarse room on one side may legitimately match several fare variants on the other — note this explicitly as a known limitation in the write-up, not hidden).
Anything below threshold stays unmatched, surfaced independently — never force-fit.

**Stage 8 — Build DB (`08_build_db.py`)**
Write everything into SQLite: `hotels`, `hotel_sources`, `near_misses`, `rooms`, `room_matches` tables.
Index `hotels.name`, `hotels.lat`, `hotels.lon`.
Also dump a flat `canonical_hotels.json` as the required submission artifact (the assignment explicitly asks for JSON/CSV output alongside the API).

**Pipeline Output / Summary**
`run_all.py` will print a final metrics table aggregating all stage logs (row counts, matches, LLM spend) into a single terminal output for easy debugging and write-up reference.

## API (FastAPI)
- `GET /health` → `{"status": "ok"}`
- `GET /hotels?search=...` → paginated list, simple LIKE search over name+address
- `GET /hotels/{id}` → full canonical record: merged fields, both source rows, matched rooms with confidence, near-miss hotel candidates
Pydantic response models in `schemas.py`; FastAPI's auto-generated OpenAPI doc satisfies the "document the contract" requirement — link `/docs` in the README.
Dockerfile + docker-compose.yml: one `docker compose up`, API loads the committed SQLite file, no external calls at runtime.

## Validation
Randomly sample ~100 candidate pairs stratified across the three score bands (not just matches).
Hand-label match/no-match.
Report precision/recall/false positive & negative examples in WRITEUP.md, with 2–3 concrete examples you can defend in the debrief (including ones you got wrong).

## Write-up checklist (WRITEUP.md, 1 page)
- Architecture diagram (the pipeline stages above).
- What you discarded (e.g. "considered brute-force LLM matching, rejected for cost").
- Validation results (precision/recall on hand-labeled sample).
- Total $ spent, broken down by stage (hotel-LLM-verification vs room-parsing).
- What breaks first at 200K hotels × 3 suppliers — likely candidates: KDTree/geohash blocking radius tuning per city density, SQLite write throughput, LLM cost scaling linearly with ambiguous-pair count (mitigations: pre-cluster by city before blocking, batch LLM calls harder, cache aggressively, consider sharding by geography).

## 48-hour timeline
| Hours | Task |
| :--- | :--- |
| 0–3 | Get CSVs, explore actual messiness, confirm stack/LLM provider, set up repo skeleton + config.yaml |
| 3–10 | Stages 1–2 (preprocess, candidates) — validate candidate recall by spot-checking known matches aren't dropped |
| 10–18 | Stage 3–4 (scoring, decision bands, LLM verification) — tune thresholds against a small manual sample as you go |
| 18–22 | Stage 5 (merge) + near-miss wiring |
| 22–30 | Stages 6–7 (room parsing + matching) |
| 30–36 | Stage 8 (SQLite) + FastAPI + Docker — get docker compose up working end-to-end early, don't leave it to the last hour |
| 36–42 | Validation sample, hand-labeling, precision/recall |
| 42–46 | Write-up |
| 46–48 | README polish, clean re-clone test, buffer |

Get the API running end-to-end (even with fake/partial data) by hour ~20 if possible — the 40%-weighted "must run from README" criterion is a hard gate, so de-risk it early rather than bolting it on at the end.

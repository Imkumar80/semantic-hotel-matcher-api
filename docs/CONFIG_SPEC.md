# Generic Entity Matcher: Configuration Specification

This document defines the standard YAML schema that must be used by the `semantic-entity-matcher` package for **any** entity type.

## Universal YAML Schema

```yaml
# ---------------------------------------------------------
# 1. Metadata & Core Identifiers
# ---------------------------------------------------------
entity_type: "products"      
description: "Match product records" 
unique_id_column: "sku"      

# ---------------------------------------------------------
# 2. Match Columns
# ---------------------------------------------------------
match_columns:
  product_name:
    type: "text"
    normalizer: "text_normalizer" 
    comparators: 
      - name: "jaro_winkler"
        thresholds: [0.9, 0.8]
      - name: "token_set"
        thresholds: [0.85, 0.7]
    weights: [0.6, 0.4]            
    field_weight: 0.35             
    
  sku:
    type: "text"
    normalizer: "none"
    comparators: 
      - name: "exact_match"
        thresholds: [] # exact match doesn't need progressive thresholds
    field_weight: 0.45
    
  price:
    type: "numeric"
    normalizer: "price_normalizer"
    comparators: 
      - name: "numeric_range"
        params: { tolerance: 0.1 }
    field_weight: 0.20

# ---------------------------------------------------------
# 3. Blocking Rules
# ---------------------------------------------------------
blocking:
  strategy: "progressive"          
  rules:
    - column: "product_name"
      type: "first_letter"
      params: { "n_chars": 1 }
    - column: "category"
      type: "exact"

# ---------------------------------------------------------
# 4. Strategy & Thresholds
# ---------------------------------------------------------
strategy:
  type: "splink"                   

thresholds:
  auto_match: 0.92                 
  llm_review: 0.75                 
  min_keep: 0.20                   

# ---------------------------------------------------------
# 5. LLM Review (Optional)
# ---------------------------------------------------------
llm:
  enabled: false
  provider: "gemini"
  model: "gemini-2.0-flash"

# ---------------------------------------------------------
# 6. Sub-Entity Matching (Optional)
# ---------------------------------------------------------
sub_entities: null                 
```

## Complete Hotel Config Example

```yaml
entity_type: "hotels"
description: "Match hotel records from two suppliers"
unique_id_column: "id"

match_columns:
  name:
    type: "text"
    normalizer: "text_normalizer"
    comparators:
      - name: "jaro_winkler"
        thresholds: [0.9, 0.8]
    field_weight: 0.35
    
  address:
    type: "text"
    normalizer: "address_normalizer"
    comparators:
      - name: "jaro_winkler"
        thresholds: [0.85, 0.7]
    field_weight: 0.25
    
  latitude:
    type: "geo"
    normalizer: "none"
    comparators:
      - name: "geo_distance"
        params: { radius_km: 2 }
    field_weight: 0.20
    
  longitude:
    type: "geo"
    normalizer: "none"
    comparators:
      - name: "geo_distance"
        params: { radius_km: 2 }
    field_weight: 0.20
    
  stars:
    type: "numeric"
    normalizer: "none"
    comparators:
      - name: "exact_match"
    field_weight: 0.10

blocking:
  strategy: "progressive"
  rules:
    - column: "name"
      type: "first_n"
      params: { n_chars: 4 }
    - column: "address"
      type: "first_n"
      params: { n_chars: 5 }

strategy:
  type: "splink"

thresholds:
  auto_match: 0.85
  llm_review: 0.65
  min_keep: 0.20

llm:
  enabled: true
  provider: "gemini"
  model: "gemini-2.5-flash"

sub_entities:
  enabled: true
  type: "rooms"
  source_file_a: "rooms_a.csv"
  source_file_b: "rooms_b.csv"
  link_column: "hotel_id"
  match_threshold: 0.65
  fields: ["name", "capacity", "bed_type"]
```

## Configuration Validation

All configs are validated using Pydantic in `src/entity_matcher/core/config.py`. Invalid configurations (e.g., using a text comparator on a numeric field) will raise explicit errors at load time rather than failing silently or unpredictably at runtime during Splink execution.

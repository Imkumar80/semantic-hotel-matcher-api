# Generic Entity Matcher: Configuration Specification

This document defines the standard YAML schema that must be used by the `semantic-entity-matcher` package for **any** entity type (hotels, products, customers, etc.). The goal is to completely decouple the codebase from any hardcoded domain assumptions.

## Universal YAML Schema

```yaml
# ---------------------------------------------------------
# 1. Metadata & Core Identifiers
# ---------------------------------------------------------
entity_type: "products"      # Identifier for the domain (e.g., hotels, products)
description: "Match product records" 

# The name of the column in the CSV representing the unique identifier
unique_id_column: "sku"      

# ---------------------------------------------------------
# 2. Match Columns
# ---------------------------------------------------------
# Defines every column that will be used for similarity scoring.
# The pipeline will dynamically apply normalizers and comparators per-column.
match_columns:
  product_name:
    type: "text"
    normalizer: "text_normalizer"  # Built-in or custom registered normalizer
    comparators: ["jaro_winkler", "token_set"]
    weights: [0.6, 0.4]            # Relative weights if using multiple comparators
    field_weight: 0.35             # Overall importance of this field in final score
    
  sku:
    type: "text"
    normalizer: "none"
    comparators: ["exact_match"]
    field_weight: 0.45
    
  price:
    type: "numeric"
    normalizer: "price_normalizer"
    comparators: ["numeric_range"]
    params: { tolerance: 0.1 }     # Custom parameters for the comparator
    field_weight: 0.20

# ---------------------------------------------------------
# 3. Blocking Rules
# ---------------------------------------------------------
# Critical for Splink performance to avoid Cartesian product comparisons
blocking:
  strategy: "progressive"          # e.g., 'progressive' or 'strict'
  rules:
    - "first_letter(product_name)" # e.g., blocks on first letter
    - "exact_match(category)"      # Custom SQL string passed to DuckDB/Splink

# ---------------------------------------------------------
# 4. Strategy & Thresholds
# ---------------------------------------------------------
strategy:
  type: "splink"                   # Could be 'embedding' or 'hybrid' in the future

thresholds:
  auto_match: 0.92                 # Minimum score to automatically merge
  llm_review: 0.75                 # Borderline scores sent to LLM for review
  min_keep: 0.20                   # Minimum score to retain as a 'near miss'

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
# See SUB_ENTITY_PATTERN.md for details
sub_entities: null                 # Use null if no child entities (e.g., products)
# For hotels, this would look like:
# sub_entities:
#   type: "rooms"
#   source_file: "rooms_a.csv"
#   link_column: "hotel_id"
#   match_threshold: 0.65
#   fields: ["name", "capacity", "bed_type"]
```

## How the Core Engine Uses This

The core pipeline will **never** hardcode column names. Instead, it iterates over `match_columns`:

```python
# Normalization Step
for col_name, col_config in config.match_columns.items():
    normalizer = get_normalizer(col_config['normalizer'])
    df[f'{col_name}_normalized'] = df[col_name].apply(normalizer.normalize)

# Splink Comparison Step
comparisons = []
for col_name, col_config in config.match_columns.items():
    for comparator_name in col_config['comparators']:
        comparisons.append(
            get_comparator(comparator_name)(col_name, col_config.get('params'))
        )
```

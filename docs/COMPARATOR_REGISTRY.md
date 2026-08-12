# Available Comparators

The `semantic-entity-matcher` maps config strings directly to instantiated Splink `ComparisonLevel` objects (or custom comparisons) via a central registry in `src/entity_matcher/comparators/registry.py`.

## Text Comparators

### `jaro_winkler`
Uses Jaro-Winkler string similarity. Requires threshold levels.
- **Valid Types**: `text`
- **YAML Example**:
```yaml
comparators:
  - name: "jaro_winkler"
    thresholds: [0.9, 0.8]
```

### `token_set`
Uses Splink's Jaccard or similar token-based set matching, good for out-of-order words.
- **Valid Types**: `text`
- **YAML Example**:
```yaml
comparators:
  - name: "token_set"
    thresholds: [0.85, 0.7]
```

### `exact_match`
Requires an exact string match. No progressive thresholds needed.
- **Valid Types**: `text`
- **YAML Example**:
```yaml
comparators:
  - name: "exact_match"
```

## Numeric Comparators

### `numeric_range`
Matches if values are within a specified distance/tolerance.
- **Valid Types**: `numeric`
- **YAML Example**:
```yaml
comparators:
  - name: "numeric_range"
    params: { tolerance: 0.1 } # E.g. within 10% or +/- 0.1
```

### `exact_match` (Numeric)
Requires an exact numeric match.
- **Valid Types**: `numeric`
- **YAML Example**:
```yaml
comparators:
  - name: "exact_match"
```

## Geospatial Comparators

### `geo_distance`
Calculates distance between coordinates using Haversine formula (or Splink's built-in array distance metrics).
- **Valid Types**: `geo`
- **YAML Example**:
```yaml
comparators:
  - name: "geo_distance"
    params: { radius_km: 2 } # E.g., matches if within 2 kilometers
```

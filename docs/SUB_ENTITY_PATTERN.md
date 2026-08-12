# Sub-Entity Matching Pattern

Sub-entities represent a 1:N relationship attached to a canonical entity (e.g., Hotels → Rooms, Products → SKUs/Variants, Papers → Sections/Chapters).

Because not all entities possess sub-entities, the generic `semantic-entity-matcher` core must **never** hardcode sub-entity matching logic. Instead, it delegates to a pluggable hook system.

## Design Architecture

1. **Core Pipeline Execution**:
   - The core pipeline runs `preprocess` → `match` → `resolve` on the primary entities (e.g., Hotels).
   - This produces a collection of resolved canonical entities (e.g., `canonical_entities.json`).
   
2. **Sub-Entity Hook Trigger**:
   - The `matcher.py` orchestrator checks the configuration.
   - If `sub_entities: null`, the pipeline completes immediately.
   - If `sub_entities` is defined, the orchestrator triggers the `SubEntityMatcher` plugin.

3. **Plugin Data Flow**:
   - The `SubEntityMatcher` receives the `canonical_entities` array and paths to the raw sub-entity CSVs.
   - It performs its own specialized matching (e.g., Bipartite Maximum Weight Matching for rooms).
   - The plugin returns `sub_entity_matches.json`.

4. **Database Builder Integration**:
   - The final output layer observes the presence of sub-entities and generates separate tables (e.g., `sub_entities` and `sub_entity_matches`) dynamically, linked via Foreign Keys.

## Configuration Definition

Sub-entities are strictly defined in the YAML config. 

### Example 1: Products (No Sub-Entities)
```yaml
sub_entities: null
```

### Example 2: Hotels (With Rooms)
```yaml
sub_entities:
  enabled: true
  type: "rooms"
  source_file_a: "rooms_a.csv"
  source_file_b: "rooms_b.csv"
  link_column: "hotel_id"        # Foreign key back to the parent entity
  match_threshold: 0.65
  fields: ["name", "capacity", "bed_type"]
```

## Plugin Interface Blueprint

The core matcher interacts with sub-entities purely through a standardized protocol:

```python
from typing import List, Dict, Any

class BaseSubEntityMatcher:
    """Interface that all sub-entity plugins must implement."""
    
    def __init__(self, config: Dict):
        self.config = config
        
    def match(self, canonical_entities: List[Dict], df_sub_a: Any, df_sub_b: Any) -> List[Dict]:
        """
        Receives parent canonical clusters and raw sub-entity data.
        Returns a list of matched sub-entity pairs.
        """
        raise NotImplementedError("Plugins must implement this method")
```

By adhering to this pattern, we ensure that hotel room logic remains securely quarantined in `examples/hotels/room_matcher.py`, completely separate from the reusable semantic matching core.

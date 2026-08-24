import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath('.'))

from src.semantic_entity_matcher import EntityMatcher, MatcherConfig

def test():
    config_dict = {
        "entity_type": "hotels",
        "id_column": "id",
        "match_columns": {
            "name": {"type": "text", "normalizer": "text_normalizer"},
            "address": {"type": "text", "normalizer": "address_normalizer"},
            "lat": {"type": "numeric", "normalizer": "numeric_normalizer"},
            "lon": {"type": "numeric", "normalizer": "numeric_normalizer"},
        },
        "strategy": "splink",
        "matching": {"auto_match_threshold": 0.84, "min_score_threshold": 0.20},
        "output": {"format": "all", "include_near_misses": True}
    }
    config = MatcherConfig(**config_dict)
    
    matcher = EntityMatcher(verbose=True)
    results = matcher.match(
        left="data/raw/supplier_a.csv",
        right="data/raw/supplier_b.csv",
        config=config,
        output_dir="data/cache/test_generic"
    )
    
    print("Metrics:", results["metrics"])
    print("Canonical items:", len(results["canonical"]))

if __name__ == "__main__":
    test()

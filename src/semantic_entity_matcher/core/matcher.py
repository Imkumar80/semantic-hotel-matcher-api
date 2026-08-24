import pandas as pd
from typing import Dict, Any, Optional
from pathlib import Path
from .config import MatcherConfig
import json
import sqlite3

class EntityMatcher:
    """
    Generic entity matching tool - works with any CSV data
    """
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.config: Optional[MatcherConfig] = None
        self.results: Optional[Dict] = None

    def match(
        self,
        left: str | pd.DataFrame,
        right: str | pd.DataFrame,
        config: str | Dict | MatcherConfig,
        output_dir: str = "./output"
    ) -> Dict[str, Any]:
        
        df_left = self._load_data(left)
        df_right = self._load_data(right)
        
        self.config = self._load_config(config)
        
        # 1. Preprocess / Normalize
        from ..pipeline.stages import preprocess
        df_left_norm = preprocess(df_left, self.config)
        df_right_norm = preprocess(df_right, self.config)
        
        # 2. Score Pairs (Strategy)
        from ..strategies import get_strategy
        strategy = get_strategy(self.config)
        scored_pairs = strategy.score_pairs(df_left_norm, df_right_norm)
        
        # 3. Resolve Graph / Merge
        from ..pipeline.resolution import resolve_and_merge
        results = resolve_and_merge(df_left_norm, df_right_norm, scored_pairs, self.config)
        
        self.results = results
        self._save_results(results, output_dir)
        
        return results

    def _load_data(self, source) -> pd.DataFrame:
        if isinstance(source, str):
            return pd.read_csv(source)
        elif isinstance(source, pd.DataFrame):
            return source.copy()
        else:
            raise ValueError(f"Unsupported source type: {type(source)}")

    def _load_config(self, config_source) -> MatcherConfig:
        if isinstance(config_source, MatcherConfig):
            return config_source
        elif isinstance(config_source, str):
            return MatcherConfig.from_yaml(config_source)
        elif isinstance(config_source, dict):
            return MatcherConfig(**config_source)
        else:
            raise ValueError(f"Unsupported config type: {type(config_source)}")

    def _save_results(self, results: Dict, output_dir: str):
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        
        if self.config.output.format in ("json", "all"):
            pd.DataFrame(results["canonical"]).to_json(path / "canonical_records.json", orient="records", indent=2)
            
        if self.config.output.format in ("csv", "all"):
            pd.DataFrame(results["canonical"]).to_csv(path / "canonical_records.csv", index=False)
            
        if self.config.output.format in ("sqlite", "all"):
            db_path = path / f"{self.config.entity_type}.db"
            if db_path.exists():
                db_path.unlink()
            conn = sqlite3.connect(db_path)
            pd.DataFrame(results["canonical"]).to_sql("entities", conn, index=False)
            if self.config.output.include_near_misses and "near_misses" in results:
                pd.DataFrame(results["near_misses"]).to_sql("near_misses", conn, index=False)
            conn.close()
            results["database_path"] = str(db_path)
            
        with open(path / "metrics.json", "w", encoding="utf-8") as f:
            json.dump(results.get("metrics", {}), f, indent=2)

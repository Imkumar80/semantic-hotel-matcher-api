import pandas as pd
from .base import BaseStrategy
from ..core.config import MatcherConfig

class SplinkStrategy(BaseStrategy):
    def score_pairs(self, df_left: pd.DataFrame, df_right: pd.DataFrame) -> pd.DataFrame:
        from splink import Linker, DuckDBAPI, block_on
        import splink.comparison_library as cl
        
        # We need a source_dataset column for link_only
        df_left = df_left.copy()
        df_right = df_right.copy()
        df_left["source_dataset"] = "left"
        df_right["source_dataset"] = "right"
        
        comparisons = []
        for col_name, col_config in self.config.match_columns.items():
            if col_name not in df_left.columns:
                continue
            
            norm_col = f"{col_name}_norm"
            if col_config.type == "text":
                comparisons.append(cl.JaroWinklerAtThresholds(norm_col, [0.9, 0.8]))
            elif col_config.type == "numeric":
                num_col = f"{col_name}_num"
                comparisons.append(cl.ExactMatch(num_col))
            elif col_config.type == "location":
                # Splink natively supports lat/lon distance if mapped
                num_col = f"{col_name}_num"
                comparisons.append(cl.ExactMatch(num_col)) # simplistic fallback
        
        if not comparisons:
            # Fallback exact match on ID if no configured columns found
            comparisons.append(cl.ExactMatch("unique_id"))
            
        settings = {
            "link_type": "link_only",
            "comparisons": comparisons,
            "retain_matching_columns": True,
            "retain_intermediate_calculation_columns": True
        }
        
        db_api = DuckDBAPI()
        # Combine datasets for Splink
        df_combined = pd.concat([df_left, df_right], ignore_index=True)
        linker = Linker(df_combined, settings, db_api=db_api)
        
        # Auto-train using deterministic rules based on the columns
        for col in self.config.match_columns:
            if col in df_left.columns:
                try:
                    linker.training.estimate_u_using_random_sampling(max_pairs=10000)
                    linker.training.estimate_parameters_using_expectation_maximisation(block_on(f"{col}_norm"))
                except Exception:
                    pass # Ignore if blocking rule fails or no data
                    
        predictions = linker.inference.predict(threshold_match_probability=self.config.matching.min_score_threshold)
        df_preds = predictions.as_pandas_dataframe()
        return df_preds

def get_strategy(config: MatcherConfig) -> BaseStrategy:
    if config.strategy == "splink":
        return SplinkStrategy(config)
    # Default to splink
    return SplinkStrategy(config)

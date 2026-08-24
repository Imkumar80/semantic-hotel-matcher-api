import pandas as pd
from ..core.config import MatcherConfig
from ..normalizers import get_normalizer

def preprocess(df: pd.DataFrame, config: MatcherConfig) -> pd.DataFrame:
    df = df.copy()
    
    # Ensure ID column exists
    if config.id_column not in df.columns:
        raise ValueError(f"ID column '{config.id_column}' not found in dataset")
        
    df["unique_id"] = df[config.id_column]
    
    # Apply normalizers to matching columns
    for col, col_config in config.match_columns.items():
        if col in df.columns:
            normalizer = get_normalizer(col_config.normalizer)
            df[f"{col}_norm"] = df[col].apply(normalizer.normalize)
            
            # Additional type-specific processing (e.g. converting numeric to float)
            if col_config.type == "numeric" or col_config.type == "location":
                df[f"{col}_num"] = pd.to_numeric(df[f"{col}_norm"], errors='coerce')
    
    return df

import pandas as pd
import os
import yaml
from splink import Linker, DuckDBAPI, block_on
import splink.comparison_library as cl

def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

def main():
    cache_dir = "data/cache"
    print("--- Splink Probabilistic Matching ---")
    
    # Load combined data
    df = pd.read_pickle(f"{cache_dir}/hotels_combined.pkl")
    df['unique_id'] = df['unique_id'].astype(str)
    
    # Fill NA for strings otherwise Splink gets mad
    for col in ['name_prefix', 'addr_numbers', 'normalized_name', 'norm_addr', 'amenities_joined']:
        df[col] = df[col].fillna('')
    df['stars'] = df['stars'].fillna(-1.0)
    
    settings = {
        "link_type": "link_only",
        "probability_two_random_records_match": 0.001,
        "source_dataset_column_name": "source_dataset",
        "unique_id_column_name": "unique_id",
        "blocking_rules_to_generate_predictions": [
            block_on("name_prefix"),
            block_on("addr_numbers")
        ],
        "comparisons": [
            cl.JaroWinklerAtThresholds("normalized_name", [0.9, 0.8]),
            cl.JaroWinklerAtThresholds("norm_addr", [0.85, 0.7]),
            cl.JaroWinklerAtThresholds("amenities_joined", [0.7, 0.4]),
            cl.ExactMatch("stars")
        ],
        "retain_intermediate_calculation_columns": True,
        "retain_matching_columns": True
    }
    
    db_api = DuckDBAPI()
    linker = Linker(df, settings, db_api=db_api)
    
    print("Training Splink model...")
    linker.training.estimate_u_using_random_sampling(max_pairs=1e5)
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("name_prefix"))
    
    print("Generating predictions...")
    df_predict = linker.inference.predict(threshold_match_probability=0.2)
    df_scored = df_predict.as_pandas_dataframe()
    
    print(f"Generated {len(df_scored)} candidate pairs.")
    
    # Reformat to match what 03_resolve_hotels expects
    results = []
    for _, row in df_scored.iterrows():
        # Ensure we always order A then B
        if 'A' in row['source_dataset_l']:
            a_id = row['unique_id_l']
            b_id = row['unique_id_r']
        else:
            a_id = row['unique_id_r']
            b_id = row['unique_id_l']
            
        results.append({
            'a_id': a_id,
            'b_id': b_id,
            'final_score': row['match_probability']
        })
        
    df_scored_formatted = pd.DataFrame(results)
    
    if df_scored_formatted.empty:
        df_scored_formatted = pd.DataFrame(columns=['a_id', 'b_id', 'final_score'])
        
    df_scored_formatted.to_pickle(f"{cache_dir}/scored_pairs.pkl")
    print("Saved scored pairs to data/cache/scored_pairs.pkl")

if __name__ == "__main__":
    main()

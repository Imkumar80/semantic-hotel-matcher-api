import pandas as pd
from splink import Linker, DuckDBAPI, block_on
import splink.comparison_library as cl
df = pd.DataFrame({'unique_id': ['1', '2'], 'source_dataset': ['A', 'B'], 'name_prefix': ['a', 'a'], 'addr_numbers': ['1', '1'], 'normalized_name': ['abc', 'abc'], 'norm_addr': ['123', '123'], 'amenities_joined': ['wifi', 'wifi'], 'stars': [5.0, 5.0]})
settings = {
    "link_type": "link_only",
    "probability_two_random_records_match": 0.01,
    "source_dataset_column_name": "source_dataset",
    "unique_id_column_name": "unique_id",
    "blocking_rules_to_generate_predictions": [
        block_on("name_prefix")
    ],
    "comparisons": [
        cl.JaroWinklerAtThresholds("normalized_name", 0.9, 0.8),
        cl.LevenshteinAtThresholds("norm_addr", 2, 5),
        cl.ExactMatch("stars")
    ]
}
try:
    db_api = DuckDBAPI()
    linker = Linker(df, settings, db_api=db_api)
    linker.training.estimate_u_using_random_sampling(max_pairs=100)
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("name_prefix"))
    preds = linker.inference.predict(threshold_match_probability=0.2)
    print(preds.as_pandas_dataframe().head())
except Exception as e:
    print(e)

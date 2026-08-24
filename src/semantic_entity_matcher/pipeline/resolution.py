import pandas as pd
from typing import Dict, Any
from ..core.config import MatcherConfig
import uuid

def resolve_and_merge(df_left: pd.DataFrame, df_right: pd.DataFrame, scored_pairs: pd.DataFrame, config: MatcherConfig) -> Dict[str, Any]:
    # We will build canonical entities here
    
    # 1. Filter by threshold
    auto_match_threshold = config.matching.auto_match_threshold
    matches = scored_pairs[scored_pairs['match_probability'] >= auto_match_threshold].copy()
    near_misses_df = scored_pairs[
        (scored_pairs['match_probability'] < auto_match_threshold) & 
        (scored_pairs['match_probability'] >= config.matching.min_score_threshold)
    ].copy()
    
    # Index left and right dataframes by unique_id for easy lookup
    left_dict = df_left.set_index('unique_id').to_dict('index')
    right_dict = df_right.set_index('unique_id').to_dict('index')
    
    canonical_records = []
    near_misses = []
    
    matched_left = set()
    matched_right = set()
    
    # Simple greedy merge (1-to-1) for demonstration. 
    # Real implementations might use NetworkX for connected components.
    # Sort matches by probability descending
    matches = matches.sort_values(by='match_probability', ascending=False)
    
    for _, row in matches.iterrows():
        id_l = row['unique_id_l']
        id_r = row['unique_id_r']
        
        if id_l in matched_left or id_r in matched_right:
            continue # already matched
            
        matched_left.add(id_l)
        matched_right.add(id_r)
        
        rec_l = left_dict.get(id_l)
        rec_r = right_dict.get(id_r)
        
        if not rec_l or not rec_r:
            continue
            
        # Merge logic
        merged = _merge_records(rec_l, rec_r, row['match_probability'], config)
        merged['source_left_id'] = id_l
        merged['source_right_id'] = id_r
        canonical_records.append(merged)
        
    # Process near misses if configured
    llm_provider = None
    if config.llm.enabled:
        from ..llm.providers import LLMProviderFactory
        llm_provider = LLMProviderFactory.get_provider(config.llm)
        
    final_near_misses_df = []
    
    for _, row in near_misses_df.iterrows():
        id_l = row['unique_id_l']
        id_r = row['unique_id_r']
        
        if id_l in matched_left or id_r in matched_right:
            continue
            
        rec_l = left_dict.get(id_l)
        rec_r = right_dict.get(id_r)
        if not rec_l or not rec_r:
            continue

        # If LLM is enabled, attempt to verify
        if llm_provider:
            # Prepare clean dicts without normalized columns for the prompt
            clean_l = {k: v for k, v in rec_l.items() if not k.endswith('_norm') and not k.endswith('_num')}
            clean_r = {k: v for k, v in rec_r.items() if not k.endswith('_norm') and not k.endswith('_num')}
            is_match, llm_conf = llm_provider.verify_match(clean_l, clean_r)
            
            if is_match:
                matched_left.add(id_l)
                matched_right.add(id_r)
                merged = _merge_records(rec_l, rec_r, row['match_probability'], config)
                merged['source_left_id'] = id_l
                merged['source_right_id'] = id_r
                # We can override confidence with LLM confidence or a combination
                merged['confidence'] = max(float(row['match_probability']), llm_conf)
                canonical_records.append(merged)
                continue # Skip adding to near_misses
                
        # If no LLM, or LLM said no match, keep it as a near miss if configured
        if config.output.include_near_misses:
            final_near_misses_df.append(row)
            
    # Unmatched left
    for id_l, rec in left_dict.items():
        if id_l not in matched_left:
            canonical = _make_canonical(rec, None, config)
            canonical['source_left_id'] = id_l
            canonical['source_right_id'] = None
            canonical_records.append(canonical)
            
    # Unmatched right
    for id_r, rec in right_dict.items():
        if id_r not in matched_right:
            canonical = _make_canonical(rec, None, config)
            canonical['source_left_id'] = None
            canonical['source_right_id'] = id_r
            canonical_records.append(canonical)
            
    if config.output.include_near_misses:
        for row in final_near_misses_df:
            near_misses.append({
                "source_left_id": row['unique_id_l'],
                "source_right_id": row['unique_id_r'],
                "score": float(row['match_probability'])
            })
            
    metrics = {
        "total_canonical": len(canonical_records),
        "total_matches": len(matches),
        "total_near_misses": len(near_misses)
    }
    
    return {
        "canonical": canonical_records,
        "near_misses": near_misses,
        "metrics": metrics
    }
    
def _merge_records(rec_l: dict, rec_r: dict, confidence: float, config: MatcherConfig) -> dict:
    canonical = {"id": str(uuid.uuid4()), "confidence": float(confidence)}
    
    # Just take left side as primary for unconfigured columns, 
    # but ideally this would also be configurable (prefer longer, non-null, etc.)
    for col in set(rec_l.keys()).union(set(rec_r.keys())):
        if col.endswith('_norm') or col.endswith('_num') or col == 'unique_id' or col == 'source_dataset':
            continue
            
        val_l = rec_l.get(col)
        val_r = rec_r.get(col)
        
        # simple heuristic: if val_l is empty/nan, take val_r
        if pd.isna(val_l) or str(val_l).strip() == "":
            canonical[col] = val_r
        elif pd.isna(val_r) or str(val_r).strip() == "":
            canonical[col] = val_l
        else:
            # If both have value, for text take longer string
            if isinstance(val_l, str) and isinstance(val_r, str):
                canonical[col] = val_l if len(val_l) >= len(val_r) else val_r
            else:
                canonical[col] = val_l
                
    return canonical

def _make_canonical(rec: dict, confidence: float, config: MatcherConfig) -> dict:
    canonical = {"id": str(uuid.uuid4()), "confidence": confidence}
    for col, val in rec.items():
        if not col.endswith('_norm') and not col.endswith('_num') and col != 'unique_id' and col != 'source_dataset':
            canonical[col] = val
    return canonical

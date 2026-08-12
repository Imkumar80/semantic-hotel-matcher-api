from pydantic import BaseModel, validator, Field
from typing import List, Dict, Any, Optional, Literal

class ComparatorConfig(BaseModel):
    name: str
    thresholds: Optional[List[float]] = []
    params: Optional[Dict[str, Any]] = {}

class MatchColumnConfig(BaseModel):
    type: Literal["text", "numeric", "geo"]
    normalizer: str = "none"
    comparators: List[ComparatorConfig]
    weights: Optional[List[float]] = None
    field_weight: float
    
    @validator('comparators')
    def validate_comparators_for_type(cls, v, values):
        """Ensure comparators are valid for the column type."""
        col_type = values.get('type')
        if not col_type:
            return v
            
        names = [c.name for c in v]
        
        if col_type == 'text':
            if 'numeric_range' in names or 'geo_distance' in names:
                raise ValueError(f"numeric_range/geo_distance comparators invalid for text type")
        
        elif col_type == 'numeric':
            if 'jaro_winkler' in names or 'token_set' in names:
                raise ValueError(f"Text comparators invalid for numeric type")
                
        elif col_type == 'geo':
            if 'jaro_winkler' in names or 'token_set' in names:
                raise ValueError(f"Text comparators invalid for geo type")
                
        return v

class BlockingRuleConfig(BaseModel):
    column: str
    type: str # 'exact', 'first_letter', 'first_n'
    params: Optional[Dict[str, Any]] = {}

class BlockingConfig(BaseModel):
    strategy: str = "progressive"
    rules: List[BlockingRuleConfig]

class ThresholdsConfig(BaseModel):
    auto_match: float
    llm_review: float
    min_keep: float

class StrategyConfig(BaseModel):
    type: str = "splink"

class LlmConfig(BaseModel):
    enabled: bool = False
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"

class SubEntitiesConfig(BaseModel):
    enabled: bool = False
    type: str
    source_file_a: str
    source_file_b: str
    link_column: str
    match_threshold: float
    fields: List[str]

class MatcherConfig(BaseModel):
    entity_type: str
    description: str
    unique_id_column: str
    match_columns: Dict[str, MatchColumnConfig]
    blocking: BlockingConfig
    strategy: StrategyConfig
    thresholds: ThresholdsConfig
    llm: Optional[LlmConfig] = Field(default_factory=LlmConfig)
    sub_entities: Optional[SubEntitiesConfig] = None
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'MatcherConfig':
        import yaml
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        return cls(**data)

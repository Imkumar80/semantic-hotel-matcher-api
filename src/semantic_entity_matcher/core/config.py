from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import yaml

class ColumnConfig(BaseModel):
    type: str = "text" # "text", "numeric", "location"
    normalizer: str = "identity" # "text_normalizer", "address_normalizer", "identity"
    comparators: List[str] = ["exact_match"] # e.g. ["jaro_winkler", "token_set_ratio"]
    params: Dict[str, Any] = Field(default_factory=dict)
    weight: float = 1.0

class MatchingConfig(BaseModel):
    auto_match_threshold: float = 0.90
    min_score_threshold: float = 0.20

class OutputConfig(BaseModel):
    format: str = "sqlite"
    include_near_misses: bool = True
    include_scores: bool = True

class LLMConfig(BaseModel):
    enabled: bool = False
    provider: str = "gemini" # gemini, openai, anthropic
    model: str = "gemini-2.5-flash"
    api_key: Optional[str] = None
    prompt_template: str = "Determine if these two {entity_type} records refer to the same real-world entity. Return JSON with 'is_match' (boolean) and 'confidence' (float 0.0-1.0)."

class MatcherConfig(BaseModel):
    entity_type: str = "entity"
    description: str = ""
    id_column: str = "id"
    match_columns: Dict[str, ColumnConfig] = Field(default_factory=dict)
    strategy: str = "splink"
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    @classmethod
    def from_yaml(cls, path: str) -> "MatcherConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)

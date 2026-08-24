from abc import ABC, abstractmethod
import pandas as pd
from ..core.config import MatcherConfig

class BaseStrategy(ABC):
    def __init__(self, config: MatcherConfig):
        self.config = config
    
    @abstractmethod
    def score_pairs(self, df_left: pd.DataFrame, df_right: pd.DataFrame) -> pd.DataFrame:
        """Return DataFrame with columns: unique_id_l, unique_id_r, match_probability"""
        pass

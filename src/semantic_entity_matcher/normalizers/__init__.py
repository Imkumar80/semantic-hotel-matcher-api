from abc import ABC, abstractmethod
import pandas as pd
import re

class BaseNormalizer(ABC):
    @abstractmethod
    def normalize(self, value: str) -> str:
        pass

class TextNormalizer(BaseNormalizer):
    def normalize(self, value: str) -> str:
        if pd.isna(value):
            return ""
        value = str(value).lower()
        value = re.sub(r'[^\w\s]', ' ', value)
        return re.sub(r'\s+', ' ', value).strip()

class AddressNormalizer(TextNormalizer):
    def normalize(self, value: str) -> str:
        value = super().normalize(value)
        stop_words = ["street", "st", "avenue", "ave", "road", "rd"]
        for word in stop_words:
            value = re.sub(rf'\b{word}\b', '', value)
        return re.sub(r'\s+', ' ', value).strip()

class NumericNormalizer(BaseNormalizer):
    def normalize(self, value: str) -> str:
        if pd.isna(value):
            return "0"
        match = re.search(r'[\d.]+', str(value))
        return match.group(0) if match else "0"

class IdentityNormalizer(BaseNormalizer):
    def normalize(self, value: str) -> str:
        return str(value) if not pd.isna(value) else ""

def get_normalizer(name: str) -> BaseNormalizer:
    if name == "text_normalizer":
        return TextNormalizer()
    elif name == "address_normalizer":
        return AddressNormalizer()
    elif name == "numeric_normalizer":
        return NumericNormalizer()
    return IdentityNormalizer()

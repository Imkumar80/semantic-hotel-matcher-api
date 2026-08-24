from typing import Tuple, Dict, Any, Optional
import os
import json
from ..core.config import LLMConfig

class BaseProvider:
    def __init__(self, config: LLMConfig):
        self.config = config

    def verify_match(self, entity_a: Dict[str, Any], entity_b: Dict[str, Any]) -> Tuple[bool, float]:
        raise NotImplementedError

class GeminiProvider(BaseProvider):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            from google import genai
            from google.genai import types
            api_key = self.config.api_key or os.getenv("GEMINI_API_KEY")
            self.client = genai.Client(api_key=api_key)
            self.types = types
        except ImportError:
            raise ImportError("Please install google-genai to use the Gemini provider.")

    def verify_match(self, entity_a: Dict[str, Any], entity_b: Dict[str, Any]) -> Tuple[bool, float]:
        prompt = self.config.prompt_template + f"\n\nRecord A:\n{json.dumps(entity_a, indent=2)}\n\nRecord B:\n{json.dumps(entity_b, indent=2)}"
        try:
            response = self.client.models.generate_content(
                model=self.config.model,
                contents=prompt,
                config=self.types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0
                )
            )
            data = json.loads(response.text)
            return bool(data.get("is_match", False)), float(data.get("confidence", 0.0))
        except Exception as e:
            print(f"Gemini LLM Error: {e}")
            return False, 0.0

class OpenAIProvider(BaseProvider):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            from openai import OpenAI
            api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
            self.client = OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError("Please install openai to use the OpenAI provider.")

    def verify_match(self, entity_a: Dict[str, Any], entity_b: Dict[str, Any]) -> Tuple[bool, float]:
        prompt = self.config.prompt_template + f"\n\nRecord A:\n{json.dumps(entity_a, indent=2)}\n\nRecord B:\n{json.dumps(entity_b, indent=2)}"
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "system", "content": "You are an entity resolution expert."}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            content = response.choices[0].message.content
            if content:
                data = json.loads(content)
                return bool(data.get("is_match", False)), float(data.get("confidence", 0.0))
            return False, 0.0
        except Exception as e:
            print(f"OpenAI LLM Error: {e}")
            return False, 0.0

class AnthropicProvider(BaseProvider):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            from anthropic import Anthropic
            api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY")
            self.client = Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError("Please install anthropic to use the Anthropic provider.")

    def verify_match(self, entity_a: Dict[str, Any], entity_b: Dict[str, Any]) -> Tuple[bool, float]:
        prompt = self.config.prompt_template + f"\n\nRecord A:\n{json.dumps(entity_a, indent=2)}\n\nRecord B:\n{json.dumps(entity_b, indent=2)}"
        try:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=256,
                temperature=0.0,
                system="You are an entity resolution expert. Always return JSON with 'is_match' (boolean) and 'confidence' (float 0.0-1.0).",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            # Find the JSON block if any
            text = response.content[0].text
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != 0:
                data = json.loads(text[start:end])
                return bool(data.get("is_match", False)), float(data.get("confidence", 0.0))
            return False, 0.0
        except Exception as e:
            print(f"Anthropic LLM Error: {e}")
            return False, 0.0

class LLMProviderFactory:
    @staticmethod
    def get_provider(config: LLMConfig) -> Optional[BaseProvider]:
        if not config.enabled:
            return None
            
        provider = config.provider.lower()
        if provider == "gemini":
            return GeminiProvider(config)
        elif provider == "openai":
            return OpenAIProvider(config)
        elif provider == "anthropic":
            return AnthropicProvider(config)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

from typing import Type, Dict, Any, TypeVar, Optional, List
from .base import LLMProvider
import json

T = TypeVar("T")

class FakeLLMProvider:
    def __init__(self):
        self.call_count = 0
        self._provider_name = "fake"
        self._model_name = "fake-model-1"
        self.responses: List[Any] = []
        self.captured_prompts: List[Dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return self._provider_name
        
    @property
    def model_name(self) -> str:
        return self._model_name

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_payload: Dict[str, Any],
        response_schema: Type[T],
    ) -> T:
        self.call_count += 1
        self.captured_prompts.append({
            "system_prompt": system_prompt,
            "user_payload": user_payload
        })
        
        if not self.responses:
            raise RuntimeError("FakeLLMProvider ran out of configured responses")

        response = self.responses.pop(0)
        
        if isinstance(response, Exception):
            raise response
        
        if isinstance(response, response_schema):
            return response
            
        if isinstance(response, dict):
            return response_schema.model_validate(response)
        
        return response_schema.model_validate_json(response)

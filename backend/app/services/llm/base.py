from typing import Protocol, Type, Dict, Any, TypeVar

T = TypeVar("T")

class LLMProvider(Protocol):
    @property
    def provider_name(self) -> str:
        ...
        
    @property
    def model_name(self) -> str:
        ...

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_payload: Dict[str, Any],
        response_schema: Type[T],
    ) -> T:
        ...

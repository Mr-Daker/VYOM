from typing import Optional
from .base import LLMProvider

# Dependency injection for FastAPI
def get_llm_provider() -> Optional[LLMProvider]:
    # Production returns None since we don't have an SDK installed yet.
    # Tests will override this dependency.
    return None

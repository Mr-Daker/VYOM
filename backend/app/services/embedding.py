from typing import List, Protocol
from app.core.curriculum_config import CURRICULUM_EMBEDDING_DIMENSION
import math

class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        ...

class FakeEmbeddingProvider:
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        results = []
        for text in texts:
            # Deterministic pseudo-random generation based on text length and ascii sum
            val = sum(ord(c) for c in text)
            length = len(text)
            vector = []
            for i in range(CURRICULUM_EMBEDDING_DIMENSION):
                # map to -1 to 1 deterministically
                v = math.sin((val + i) * length)
                vector.append(round(v, 6))
            results.append(vector)
        return results


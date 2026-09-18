"""Small, inspectable retrieval layer over an approved curriculum corpus."""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from functools import lru_cache
from typing import Any, Dict, List


CORPUS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "curriculum_corpus.json")


class RetrievalError(Exception):
    pass


@lru_cache(maxsize=1)
def load_corpus() -> List[Dict[str, Any]]:
    try:
        with open(CORPUS_PATH, "r", encoding="utf-8") as handle:
            corpus = json.load(handle)
    except FileNotFoundError as exc:
        raise RetrievalError("curriculum corpus file not found") from exc
    except json.JSONDecodeError as exc:
        raise RetrievalError("curriculum corpus is malformed") from exc
    if not isinstance(corpus, list) or not corpus:
        raise RetrievalError("curriculum corpus must be a non-empty list")
    required = {"subject", "grade", "competency_id", "language", "source_reference", "content"}
    for index, item in enumerate(corpus):
        if not isinstance(item, dict) or not required.issubset(item):
            raise RetrievalError(f"curriculum item {index} is missing required metadata")
    return corpus


def _tokens(text: str) -> Counter:
    return Counter(re.findall(r"[\w\u0900-\u097f]+", text.lower()))


def _cosine(left: Counter, right: Counter) -> float:
    dot = sum(value * right.get(key, 0) for key, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def search_curriculum(query: str, language: str = "English", limit: int = 3) -> List[Dict[str, Any]]:
    """Rank approved chunks using a deterministic bag-of-words embedding."""

    query_vector = _tokens(query)
    scored = []
    for item in load_corpus():
        language_bonus = 0.25 if item["language"] == language else 0.0
        text = f"{item['competency_id']} {item['subject']} {item['content']}"
        score = _cosine(query_vector, _tokens(text)) + language_bonus
        scored.append((score, item))
    return [dict(item, retrieval_score=round(score, 4)) for score, item in sorted(scored, key=lambda pair: -pair[0])[:limit]]


def get_curriculum_context(competency_id: str, language: str = "English") -> Dict[str, Any]:
    exact = [
        item for item in load_corpus()
        if item["competency_id"] == competency_id and item["language"] == language
    ]
    if not exact and language != "English":
        exact = [
            item for item in load_corpus()
            if item["competency_id"] == competency_id and item["language"] == "English"
        ]
    if not exact:
        raise RetrievalError(f"no approved curriculum context for {competency_id}")
    item = dict(exact[0])
    item["retrieval_method"] = "approved-metadata + lexical-embedding"
    return item


def source_is_approved(reference: str, competency_id: str) -> bool:
    return any(
        item["competency_id"] == competency_id and item["source_reference"] == reference
        for item in load_corpus()
    )

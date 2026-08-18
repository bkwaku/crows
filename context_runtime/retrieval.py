from __future__ import annotations

import math
import re
from collections import Counter

from .models import Capability, RetrievalMatch


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_STOP_WORDS = {
    "a", "an", "and", "are", "be", "for", "from", "if", "is", "it",
    "of", "or", "should", "the", "this", "to", "whether", "with",
}


def tokenize(text: str) -> list[str]:
    expanded = _CAMEL_BOUNDARY.sub(" ", text.replace("_", " ").replace(".", " "))
    return [
        token.lower()
        for token in _TOKEN_PATTERN.findall(expanded)
        if token.lower() not in _STOP_WORDS
    ]


class BM25Retriever:
    def __init__(self, *, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

    def match(
        self,
        need: str,
        capabilities: list[Capability] | tuple[Capability, ...],
    ) -> RetrievalMatch | None:
        if not capabilities:
            return None
        documents = [tokenize(capability.search_document) for capability in capabilities]
        query = set(tokenize(need))
        if not query:
            return None
        average_length = sum(map(len, documents)) / max(len(documents), 1)
        document_frequency = Counter(
            token for document in documents for token in set(document)
        )

        ranked: list[tuple[float, Capability]] = []
        for capability, document in zip(capabilities, documents, strict=True):
            frequencies = Counter(document)
            score = 0.0
            for token in query:
                frequency = frequencies[token]
                if not frequency:
                    continue
                frequency_in_docs = document_frequency[token]
                inverse_document_frequency = math.log(
                    1 + (len(documents) - frequency_in_docs + 0.5)
                    / (frequency_in_docs + 0.5)
                )
                normalization = frequency + self.k1 * (
                    1 - self.b + self.b * len(document) / max(average_length, 1)
                )
                score += inverse_document_frequency * (
                    frequency * (self.k1 + 1) / normalization
                )
            ranked.append((score, capability))

        ranked.sort(key=lambda item: (-item[0], item[1].qualified_name))
        best_score, best_capability = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        if best_score <= 0:
            return None
        return RetrievalMatch(best_capability, best_score, runner_up)


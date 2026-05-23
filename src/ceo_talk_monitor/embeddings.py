from __future__ import annotations

import hashlib
import math
from functools import cached_property


class Embedder:
    def __init__(self, model_name: str):
        self.model_name = model_name

    @cached_property
    def _fastembed_model(self):
        try:
            from fastembed import TextEmbedding

            return TextEmbedding(model_name=self.model_name)
        except Exception:
            return None

    @property
    def size(self) -> int:
        if self._fastembed_model is None:
            return 384
        vector = next(self._fastembed_model.embed(["dimension probe"]))
        return len(vector)

    def embed(self, text: str) -> list[float]:
        if self._fastembed_model is not None:
            vector = next(self._fastembed_model.embed([text]))
            return [float(value) for value in vector]
        return _hash_embedding(text, 384)


def _hash_embedding(text: str, size: int) -> list[float]:
    vector = [0.0] * size
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % size
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


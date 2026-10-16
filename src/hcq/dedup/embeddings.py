"""Text embeddings through a local Ollama server (e.g. ``bge-m3``, multilingual).

Optional for duplicate detection: enable with HCQ_EMBEDDINGS=ollama.
"""

from __future__ import annotations

from typing import Protocol

import httpx
import numpy as np

from hcq.config import Settings


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, d) array of L2-normalised vectors."""
        ...


class OllamaEmbedder:
    def __init__(
        self,
        base_url: str,
        model: str,
        batch_size: int = 64,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self.batch_size = batch_size
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            resp = self._client.post(
                "/api/embed",
                json={"model": self.model, "input": texts[start : start + self.batch_size]},
            )
            resp.raise_for_status()
            vectors.extend(resp.json()["embeddings"])
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.size == 0:
            return arr.reshape(0, 0)
        return arr / np.clip(np.linalg.norm(arr, axis=1, keepdims=True), 1e-12, None)


def get_embedder(settings: Settings) -> Embedder | None:
    if settings.embeddings == "ollama":
        return OllamaEmbedder(settings.ollama_url, settings.embed_model)
    return None

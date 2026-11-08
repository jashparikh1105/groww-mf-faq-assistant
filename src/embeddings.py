"""Embedding backends for sentence-transformers/all-MiniLM-L6-v2.

- "sentence-transformers": the official library (used on your laptop for ingestion).
- "onnx": the same all-MiniLM-L6-v2 weights exported to ONNX, run with onnxruntime
          (bundled with chromadb). Same mean-pooling + L2-normalisation, so vectors match,
          but no PyTorch is needed — fits a 512 MB free server.
Choose with EMBEDDING_BACKEND in .env.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from src.config import env, get_config, path


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, batch_size: int, normalize: bool):
        from sentence_transformers import SentenceTransformer  # heavy import, lazy

        self.model = SentenceTransformer(model_name, cache_folder=str(path("model_cache_dir")))
        self.batch_size = batch_size
        self.normalize = normalize
        self.name = f"sentence-transformers:{model_name}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = self.model.encode(
            texts, batch_size=self.batch_size, normalize_embeddings=self.normalize, show_progress_bar=len(texts) > 32
        )
        return [v.tolist() for v in vecs]


class OnnxMiniLMEmbedder:
    def __init__(self):
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

        cache = path("model_cache_dir") / "onnx_models" / ONNXMiniLM_L6_V2.MODEL_NAME

        class _Local(ONNXMiniLM_L6_V2):  # keep the model inside the project folder
            DOWNLOAD_PATH = cache

        self.fn = _Local(preferred_providers=["CPUExecutionProvider"])
        self.name = "onnx:all-MiniLM-L6-v2"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self.fn(texts)]


class HashingEmbedder:
    """OFFLINE TESTS ONLY: deterministic bag-of-words hashing (no model download).
    Lets the automated tests run without internet. Never use for the real app."""

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.name = "hashing-test-only"

    def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib
        import math
        import re

        out = []
        for t in texts:
            v = [0.0] * self.dim
            for tok in re.findall(r"[a-z0-9]+", t.lower()):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                v[h % self.dim] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    cfg = get_config()["embedding"]
    backend = env("EMBEDDING_BACKEND", "sentence-transformers").lower()
    if backend == "onnx":
        return OnnxMiniLMEmbedder()
    if backend == "hashing":
        return HashingEmbedder(cfg["dimension"])
    return SentenceTransformerEmbedder(cfg["model_name"], cfg["batch_size"], cfg["normalize"])

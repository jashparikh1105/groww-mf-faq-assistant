"""Retriever: same embedding model + same ChromaDB collection as ingestion.

Hybrid retrieval = metadata filter (scheme) + vector similarity, with the exact fact card
(e.g. hdfc-mid-cap::fact::exit_load) pinned to the top when the fact type is known.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import chromadb
from chromadb.config import Settings

from src.config import get_config, path
from src.embeddings import get_embedder


@dataclass
class Hit:
    id: str
    text: str
    metadata: dict
    distance: float
    pinned: bool = False


@lru_cache(maxsize=1)
def get_collection():
    client = chromadb.PersistentClient(path=str(path("vector_db_dir")), settings=Settings(anonymized_telemetry=False))
    return client.get_collection(get_config()["vector_db"]["collection_name"])


def _fact_card(scheme: str | None, fact: str) -> Hit | None:
    col = get_collection()
    where = {"$and": [{"scheme": scheme}, {"fact_type": fact}]} if scheme else {"fact_type": fact}
    res = col.get(where=where, limit=1, include=["documents", "metadatas"])
    if res["ids"]:
        return Hit(res["ids"][0], res["documents"][0], res["metadatas"][0], 0.0, pinned=True)
    return None


def retrieve(question: str, scheme: str | None = None, fact: str | None = None, top_k: int | None = None) -> list[Hit]:
    cfg = get_config()["retrieval"]
    k = top_k or cfg["top_k"]
    col = get_collection()
    qvec = get_embedder().embed([question])[0]
    kwargs = {"query_embeddings": [qvec], "n_results": k, "include": ["documents", "metadatas", "distances"]}
    if scheme:
        kwargs["where"] = {"scheme": scheme}
    res = col.query(**kwargs)
    hits = [
        Hit(i, d, m, float(dist))
        for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]

    if fact:
        card = _fact_card(scheme, fact)
        if card:
            hits = [card] + [h for h in hits if h.id != card.id]
    return hits[:k]


def is_confident(hits: list[Hit]) -> bool:
    if not hits:
        return False
    if hits[0].pinned:
        return True
    return hits[0].distance <= get_config()["retrieval"]["max_distance"]

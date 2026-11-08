"""Phase 6 — Store chunks + embeddings in ChromaDB (persistent, cosine distance).

Run:  python -m src.phase6_store
Out:  vector_db/  +  data/vectordb_report.json
"""
from __future__ import annotations

import json
from datetime import datetime

import chromadb
from chromadb.config import Settings

from src.config import get_config, path


def get_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=str(path("vector_db_dir")), settings=Settings(anonymized_telemetry=False))


def store_all() -> dict:
    cfg = get_config()
    chunks = json.loads((path("chunks_dir") / "chunks.json").read_text(encoding="utf-8"))
    embs = {r["id"]: r["vector"] for r in json.loads((path("embeddings_dir") / "embeddings.json").read_text(encoding="utf-8"))}
    missing = [c["id"] for c in chunks if c["id"] not in embs]
    if missing:
        raise SystemExit(f"{len(missing)} chunks have no embedding — re-run phase 5. First: {missing[:3]}")

    client = get_client()
    name = cfg["vector_db"]["collection_name"]
    try:
        client.delete_collection(name)  # idempotent rebuild
    except Exception:  # noqa: BLE001 - collection may not exist yet
        pass
    col = client.create_collection(name=name, metadata={"hnsw:space": cfg["vector_db"]["distance"]})

    batch = 100
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        col.upsert(
            ids=[c["id"] for c in part],
            documents=[c["text"] for c in part],
            embeddings=[embs[c["id"]] for c in part],
            metadatas=[c["metadata"] for c in part],
        )

    count = col.count()
    report = {
        "collection": name,
        "distance": cfg["vector_db"]["distance"],
        "chunks_in_file": len(chunks),
        "vectors_in_db": count,
        "all_present": count == len(chunks),
        "path": path("vector_db_dir").name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (path("chunks_dir").parent / "vectordb_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("Phase 6 complete." if report["all_present"] else "WARNING: count mismatch!")
    return report


if __name__ == "__main__":
    store_all()

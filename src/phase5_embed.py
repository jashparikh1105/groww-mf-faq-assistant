"""Phase 5 — Embed every chunk with sentence-transformers/all-MiniLM-L6-v2.

Run:  python -m src.phase5_embed
Out:  data/embeddings/embeddings.json  +  data/embeddings/embedding_meta.json
"""
from __future__ import annotations

import json
import time
from datetime import datetime

from src.config import get_config, path
from src.embeddings import get_embedder


def embed_all() -> list[dict]:
    cfg = get_config()
    chunks = json.loads((path("chunks_dir") / "chunks.json").read_text(encoding="utf-8"))
    out_dir = path("embeddings_dir")
    out_dir.mkdir(parents=True, exist_ok=True)

    embedder = get_embedder()
    print(f"Embedding {len(chunks)} chunks with {embedder.name} ...")
    t0 = time.time()
    vectors = embedder.embed([c["text"] for c in chunks])
    secs = round(time.time() - t0, 2)

    records = [{"id": c["id"], "vector": [round(x, 6) for x in v]} for c, v in zip(chunks, vectors)]
    (out_dir / "embeddings.json").write_text(json.dumps(records), encoding="utf-8")
    dim = len(vectors[0]) if vectors else 0
    meta = {
        "model": cfg["embedding"]["model_name"],
        "backend": embedder.name,
        "dimension": dim,
        "normalized": cfg["embedding"]["normalize"],
        "count": len(records),
        "seconds": secs,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (out_dir / "embedding_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))
    print(f"Phase 5 complete: {len(records)} vectors of size {dim} -> {out_dir}")
    if dim != cfg["embedding"]["dimension"]:
        print(f"WARNING: expected dimension {cfg['embedding']['dimension']}, got {dim}")
    return records


if __name__ == "__main__":
    embed_all()

"""Are all the chunks present in the vector DB?  Compares every chunk id in chunks.json with ChromaDB."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chromadb  # noqa: E402
from chromadb.config import Settings  # noqa: E402

from src.config import get_config, path  # noqa: E402


def main() -> None:
    chunks = json.loads((path("chunks_dir") / "chunks.json").read_text(encoding="utf-8"))
    col = chromadb.PersistentClient(path=str(path("vector_db_dir")), settings=Settings(anonymized_telemetry=False)).get_collection(get_config()["vector_db"]["collection_name"])
    stored = set(col.get(include=[])["ids"])
    expected = {c["id"] for c in chunks}
    missing, extra = expected - stored, stored - expected
    print(f"chunks.json : {len(expected)}")
    print(f"ChromaDB    : {len(stored)}")
    print(f"missing     : {len(missing)} {sorted(missing)[:5]}")
    print(f"extra       : {len(extra)} {sorted(extra)[:5]}")
    by_doc: dict[str, int] = {}
    for m in col.get(include=["metadatas"])["metadatas"]:
        by_doc[m["doc_id"]] = by_doc.get(m["doc_id"], 0) + 1
    print("per document:", json.dumps(by_doc, indent=2))
    sample = col.get(limit=2, include=["documents", "embeddings"])
    for i, d, e in zip(sample["ids"], sample["documents"], sample["embeddings"]):
        print(f"\nsample id={i}\n  text={d[:120]!r}\n  vector dim={len(e)} first3={[round(float(x), 4) for x in e[:3]]}")
    if missing or extra:
        sys.exit("NOT all chunks are present — re-run phase 6.")
    print("\nYES — all chunks are present in the vector DB.")


if __name__ == "__main__":
    main()

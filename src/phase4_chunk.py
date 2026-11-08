"""Phase 4 — Chunking (fact cards + FAQ pairs + heading-aware section chunks).

Run:  python -m src.phase4_chunk
Out:  data/chunks/chunks.json  +  data/chunks/chunk_stats.json

Why this strategy?  Groww pages are mostly short "label -> value" facts, a few prose
sections and an FAQ block. A plain fixed-size splitter would put many unrelated facts in
one chunk, so retrieval for "exit load" could return the "expense ratio" chunk. We therefore
make one self-describing chunk per fact, keep each Q&A pair together, and only split prose.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter

from src.config import get_config, path


def recursive_split(text: str, size: int, overlap: int, separators: list[str]) -> list[str]:
    """Split text into pieces <= size chars, preferring natural boundaries, with overlap."""
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []

    # find the best separator that actually occurs
    sep = next((s for s in separators if s in text), "")
    parts = text.split(sep) if sep else [text[i:i + size] for i in range(0, len(text), size)]

    chunks, current = [], ""
    for part in parts:
        piece = part if not current else current + sep + part
        if len(piece) <= size:
            current = piece
            continue
        if current:
            chunks.append(current)
        if len(part) > size:  # still too long -> go one level deeper
            deeper = separators[separators.index(sep) + 1:] if sep in separators else []
            chunks.extend(recursive_split(part, size, 0, deeper or [""]))  # overlap added once, below
            current = ""
        else:
            current = part
    if current:
        chunks.append(current)

    # add overlap: prepend the tail of the previous chunk
    if overlap > 0 and len(chunks) > 1:
        with_overlap = [chunks[0]]
        for prev, cur in zip(chunks, chunks[1:]):
            tail = prev[-overlap:]
            cut = tail.find(" ")
            tail = tail[cut + 1:] if cut != -1 else tail
            with_overlap.append((tail + " " + cur).strip())
        chunks = with_overlap
    return [c.strip() for c in chunks if c.strip()]


def _meta(doc: dict, chunk_type: str, **extra) -> dict:
    m = {
        "doc_id": doc["doc_id"],
        "scheme": doc["doc_id"],
        "scheme_name": doc["scheme_name"],
        "page_type": doc["page_type"],
        "category": doc["category"],
        "chunk_type": chunk_type,
        "source_url": doc["url"],
        "scraped_at": doc["scraped_at"],
        "fact_type": "",
        "section": "",
    }
    m.update(extra)
    return m


def chunk_document(doc: dict, cfg: dict) -> list[dict]:
    c = cfg["chunking"]
    name = doc["scheme_name"]
    chunks: list[dict] = []

    # 1) fact cards
    for fact, value in doc.get("facts", {}).items():
        label = doc.get("fact_labels", {}).get(fact, fact.replace("_", " ").title())
        value = str(value).rstrip(". ")
        if value.lower().startswith(label.lower()):      # e.g. "Exit load of 1% ..." -> no repeated label
            text = f"{name} — {value}."
        else:
            text = f"{name} — {label}: {value}."
        if fact == "lock_in" and doc.get("category") == "ELSS":
            text = f"{name} — {label}: {value} (ELSS tax-saver schemes have a statutory lock-in)."
        chunks.append({
            "id": f"{doc['doc_id']}::fact::{fact}",
            "text": text,
            "metadata": _meta(doc, "fact", fact_type=fact, section="Key facts"),
        })

    # 2) FAQ pairs
    for i, faq in enumerate(doc.get("faqs", [])):
        text = f"{name} | FAQ\nQ: {faq['q']}\nA: {faq['a']}"
        for j, piece in enumerate(recursive_split(text, c["chunk_size"] * 2, 0, c["separators"])):
            chunks.append({
                "id": f"{doc['doc_id']}::faq::{i}::{j}",
                "text": piece,
                "metadata": _meta(doc, "faq", section="FAQ"),
            })

    # 3) section chunks with contextual prefix
    for si, sec in enumerate(doc.get("sections", [])):
        prefix = f"{name} | {sec['heading']}:\n"
        for j, piece in enumerate(recursive_split(sec["text"], c["chunk_size"], c["chunk_overlap"], c["separators"])):
            if len(piece) < c["min_chunk_chars"]:
                continue
            chunks.append({
                "id": f"{doc['doc_id']}::section::{si}::{j}",
                "text": prefix + piece,
                "metadata": _meta(doc, "section", section=sec["heading"][:120]),
            })

    # de-duplicate identical texts
    seen, unique = set(), []
    for ch in chunks:
        h = hashlib.md5(ch["text"].encode("utf-8")).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        unique.append(ch)
    return unique


def chunk_all() -> list[dict]:
    cfg = get_config()
    loaded_dir, out_dir = path("loaded_dir"), path("chunks_dir")
    out_dir.mkdir(parents=True, exist_ok=True)

    all_chunks: list[dict] = []
    for f in sorted(loaded_dir.glob("*.json")):
        if f.name == "load_report.json":
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        chunks = chunk_document(doc, cfg)
        all_chunks.extend(chunks)
        print(f"[ok] {doc['doc_id']}: {len(chunks)} chunks")

    (out_dir / "chunks.json").write_text(json.dumps(all_chunks, indent=2, ensure_ascii=False), encoding="utf-8")
    lengths = [len(c["text"]) for c in all_chunks] or [0]
    stats = {
        "strategy": cfg["chunking"]["strategy"],
        "chunk_size": cfg["chunking"]["chunk_size"],
        "chunk_overlap": cfg["chunking"]["chunk_overlap"],
        "total_chunks": len(all_chunks),
        "by_doc": dict(Counter(c["metadata"]["doc_id"] for c in all_chunks)),
        "by_type": dict(Counter(c["metadata"]["chunk_type"] for c in all_chunks)),
        "avg_chars": round(sum(lengths) / len(lengths), 1),
        "max_chars": max(lengths),
        "min_chars": min(lengths),
    }
    (out_dir / "chunk_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"\nPhase 4 complete: {len(all_chunks)} chunks -> {out_dir / 'chunks.json'}")
    print(json.dumps(stats, indent=2))
    return all_chunks


if __name__ == "__main__":
    chunk_all()

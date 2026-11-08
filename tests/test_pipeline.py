"""Loading, chunking and vector-store checks on the fixture corpus."""
import json

import chromadb
from chromadb.config import Settings

from src.config import get_config, path


def _doc(doc_id):
    return json.loads((path("loaded_dir") / f"{doc_id}.json").read_text(encoding="utf-8"))


def test_facts_from_embedded_json_use_main_scheme_not_similar_funds():
    d = _doc("hdfc-mid-cap")
    assert d["facts"]["expense_ratio"] == "0.22%"          # not 9.99 from similar_funds
    assert d["facts"]["min_sip"] == "₹221"
    assert d["facts"]["risk"] == "Very High risk"
    assert "Midcap 150" in d["facts"]["benchmark"]
    assert d["facts"]["fund_manager"] == "Fixture Manager One, Fixture Manager Two"


def test_elss_lock_in_parsed_from_dict():
    assert _doc("hdfc-elss")["facts"]["lock_in"] == "3 years"


def test_regex_fallback_without_embedded_json():
    f = _doc("hdfc-flexi-cap")["facts"]
    assert f["expense_ratio"] == "0.44%"
    assert f["min_sip"] == "₹444"
    assert f["min_lumpsum"] == "₹445"
    assert f["risk"].lower().startswith("very high")
    assert f["exit_load"].startswith("Exit load of 1%")
    assert "NIFTY 500" in f["benchmark"]


def test_faqs_and_sections_loaded():
    d = _doc("hdfc-large-cap")
    assert len(d["faqs"]) == 2
    assert any("Exit load" in s["heading"] for s in d["sections"])
    assert all("Login" not in s["text"] for s in d["sections"])   # nav removed


def test_chunks_have_required_metadata():
    chunks = json.loads((path("chunks_dir") / "chunks.json").read_text(encoding="utf-8"))
    assert chunks
    types = {c["metadata"]["chunk_type"] for c in chunks}
    assert types == {"fact", "faq", "section"}
    for c in chunks:
        m = c["metadata"]
        assert m["source_url"].startswith("https://groww.in/")
        assert m["scraped_at"] == "2026-11-08"
        if m["chunk_type"] == "section":
            assert len(c["text"]) <= get_config()["chunking"]["chunk_size"] + 250


def test_all_chunks_in_vector_db():
    chunks = json.loads((path("chunks_dir") / "chunks.json").read_text(encoding="utf-8"))
    col = chromadb.PersistentClient(path=str(path("vector_db_dir")), settings=Settings(anonymized_telemetry=False)).get_collection(get_config()["vector_db"]["collection_name"])
    assert col.count() == len(chunks)
    assert set(col.get(include=[])["ids"]) == {c["id"] for c in chunks}


def test_recursive_split_respects_size():
    from src.phase4_chunk import recursive_split
    text = ("Sentence number one is here. " * 120).strip()
    parts = recursive_split(text, 300, 50, ["\n\n", "\n", ". ", " "])
    assert len(parts) > 1
    assert all(len(p) <= 300 + 60 for p in parts)

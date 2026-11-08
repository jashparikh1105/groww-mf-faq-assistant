"""Test setup: builds an isolated corpus from FAKE fixture pages in a temp folder and runs
phases 3-6 on it with an offline embedder, so tests need no internet and never touch data/."""
import os
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="mf_faq_test_"))
_cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
_cfg["paths"] = {
    "raw_dir": str(_TMP / "raw"), "loaded_dir": str(_TMP / "loaded"), "chunks_dir": str(_TMP / "chunks"),
    "embeddings_dir": str(_TMP / "embeddings"), "vector_db_dir": str(_TMP / "vector_db"),
    "model_cache_dir": str(_TMP / "models"),
}
_cfg["retrieval"]["max_distance"] = 0.95   # hashing embedder is weaker than MiniLM
(_TMP / "config.yaml").write_text(yaml.safe_dump(_cfg, allow_unicode=True), encoding="utf-8")

os.environ["MF_CONFIG"] = str(_TMP / "config.yaml")
os.environ["EMBEDDING_BACKEND"] = "hashing"
os.environ["LLM_PROVIDER"] = "groq"
os.environ["GROQ_API_KEY"] = ""          # force the extractive (no-LLM) path in tests

from tests.fixtures.make_fixtures import write_all  # noqa: E402

write_all(_TMP / "raw")

from src.phase3_load import load_all  # noqa: E402
from src.phase4_chunk import chunk_all  # noqa: E402
from src.phase5_embed import embed_all  # noqa: E402
from src.phase6_store import store_all  # noqa: E402

load_all()
chunk_all()
embed_all()
store_all()

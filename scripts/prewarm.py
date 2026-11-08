"""Download the embedding model at build time so the first user request is fast (used on Render)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.embeddings import get_embedder  # noqa: E402

vec = get_embedder().embed(["warm up"])[0]
print(f"Embedding model ready ({len(vec)} dims).")

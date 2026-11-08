"""Prove that the server's ONNX MiniLM gives the same vectors as sentence-transformers.

Needs requirements-ingest.txt installed.  Expected: cosine similarity ≈ 1.0000 for every text.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from src.config import get_config  # noqa: E402
from src.embeddings import OnnxMiniLMEmbedder, SentenceTransformerEmbedder  # noqa: E402

TEXTS = [
    "What is the expense ratio of HDFC Mid Cap Fund?",
    "HDFC ELSS Tax Saver Fund Direct Plan Growth — Lock-in period: 3 years.",
    "Exit load of 1% if redeemed within 1 year",
]


def main() -> None:
    c = get_config()["embedding"]
    st = SentenceTransformerEmbedder(c["model_name"], c["batch_size"], True).embed(TEXTS)
    ox = OnnxMiniLMEmbedder().embed(TEXTS)
    for t, a, b in zip(TEXTS, st, ox):
        a, b = np.array(a), np.array(b)
        print(f"{float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b))):.6f}  {t}")


if __name__ == "__main__":
    main()

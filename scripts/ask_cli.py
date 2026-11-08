"""Ask a question from the terminal (tests Phase 7 without the UI).

  python scripts/ask_cli.py "What is the exit load of HDFC Mid Cap Fund?"
  python scripts/ask_cli.py --debug "ELSS lock-in?"     # also shows retrieved chunks
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.answer import answer_question  # noqa: E402
from src.rag.guardrails import classify  # noqa: E402
from src.rag.retriever import retrieve  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="+")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    q = " ".join(a.question)
    if a.debug:
        intent = classify(q)
        print(f"intent={intent}")
        scheme = (intent.schemes or [None])[0]
        for h in retrieve(q, scheme=scheme, fact=intent.fact):
            print(f"  {h.distance:.3f} {'PIN' if h.pinned else '   '} {h.id}: {h.text[:100]!r}")
        print()
    r = answer_question(q)
    print(f"[{r['type']}] model={r['model']}\n{r['text']}")


if __name__ == "__main__":
    main()

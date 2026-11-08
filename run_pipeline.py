"""Run the full ingestion pipeline (phases 1-6) or a single phase.

  python run_pipeline.py              # all phases
  python run_pipeline.py --from 3     # start at loading (re-uses saved raw HTML)
  python run_pipeline.py --only 4     # just chunking
"""
import argparse
import subprocess
import sys

PHASES = {
    1: ("Creating directories", [sys.executable, "scripts/setup_dirs.py"]),
    2: ("Scraping documents", [sys.executable, "-m", "src.phase2_scrape"]),
    3: ("Loading documents", [sys.executable, "-m", "src.phase3_load"]),
    4: ("Chunking", [sys.executable, "-m", "src.phase4_chunk"]),
    5: ("Embedding", [sys.executable, "-m", "src.phase5_embed"]),
    6: ("Storing in ChromaDB", [sys.executable, "-m", "src.phase6_store"]),
    7: ("Verifying vector DB", [sys.executable, "scripts/verify_vector_db.py"]),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--only", type=int)
    args = ap.parse_args()
    todo = [args.only] if args.only else [p for p in PHASES if p >= args.start]
    for p in todo:
        name, cmd = PHASES[p]
        print(f"\n{'=' * 70}\nPHASE {p}: {name}\n{'=' * 70}")
        if subprocess.call(cmd) != 0:
            sys.exit(f"Phase {p} failed — fix the error above and re-run with --from {p}")
    print("\nAll done. Start the app with:  uvicorn src.api:app --reload")


if __name__ == "__main__":
    main()

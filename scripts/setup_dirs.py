"""Phase 1 — create the project data directories listed in config.yaml."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_config, path  # noqa: E402


def main() -> None:
    for key in get_config()["paths"]:
        p = path(key)
        p.mkdir(parents=True, exist_ok=True)
        print(f"[ok] {p}")
    print("Phase 1 complete: directories ready.")


if __name__ == "__main__":
    main()

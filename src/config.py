"""Loads config/config.yaml and .env into one settings object."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.getenv("MF_CONFIG", str(ROOT / "config" / "config.yaml")))

load_dotenv(ROOT / ".env")


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg


def path(key: str) -> Path:
    """Absolute path for an entry in config.paths."""
    return ROOT / get_config()["paths"][key]


def sources() -> list[dict[str, Any]]:
    return get_config()["sources"]


def source_by_id(doc_id: str) -> dict[str, Any] | None:
    for s in sources():
        if s["doc_id"] == doc_id:
            return s
    return None


def env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else default

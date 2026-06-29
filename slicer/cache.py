from __future__ import annotations
import hashlib
import json
import os
import tempfile
from pathlib import Path

from .extractor import extract_function_inventory

SLICER_VERSION = "v3"
CACHE_DIR = Path(".impactguard_cache")


def cache_key(file_path: Path) -> str:
    content = file_path.read_bytes()
    return hashlib.sha256(content + SLICER_VERSION.encode()).hexdigest()


def load_or_parse(file_path: Path) -> dict:
    key = cache_key(file_path)
    cache_file = CACHE_DIR / f"{key}.json"

    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    inventory = extract_function_inventory(file_path)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=CACHE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(inventory, f)
        os.replace(tmp_path, cache_file)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return inventory

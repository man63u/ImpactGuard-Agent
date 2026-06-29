from __future__ import annotations
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from slicer.cache import load_or_parse


def _worker(file_path: Path) -> tuple[str, dict]:
    return str(file_path), load_or_parse(file_path)


def build_inventory_for_files(files: list[Path]) -> dict:
    """Parse all files in parallel using ProcessPoolExecutor.

    Returns {str(file_path): extract_function_inventory result}.
    ProcessPoolExecutor is used (not ThreadPoolExecutor) to bypass the GIL
    for CPU-bound Tree-sitter parsing.
    """
    if not files:
        return {}

    inventory: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
        futures = {pool.submit(_worker, f): f for f in files}
        for future in as_completed(futures):
            path_str, result = future.result()
            inventory[path_str] = result

    return inventory

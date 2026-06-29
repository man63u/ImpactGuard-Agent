from pathlib import Path
import pytest
from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from slicer2.call_graph import build_call_graph_context, build_call_index, uri_to_relpath
from slicer.extractor import extract_function_inventory

FIXTURES = Path(__file__).parent / "fixtures"


def _start_lsp(repo_root: Path) -> SyncLanguageServer:
    config = MultilspyConfig.from_dict({"code_language": "python"})
    return SyncLanguageServer.create(config, MultilspyLogger(), str(repo_root))


def test_caller_found_via_bfs(tmp_path, monkeypatch):
    """BFS from helper discovers caller; import ref is not counted as a caller."""
    import slicer.cache as cache_mod
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / ".cache")

    repo = FIXTURES / "fixture_a"
    lsp = _start_lsp(repo)
    with lsp.start_server():
        result = build_call_graph_context(
            [{"file": "lib.py", "key": "helper"}],
            lsp,
            repo,
            inventory_cache={},
            call_index_cache={},
            max_depth=1,
        )

    assert ("lib.py", "helper") in result
    assert ("main.py", "caller") in result, (
        "caller() in main.py should be discovered as a fan-in of helper"
    )


def test_definition_itself_filtered_out(tmp_path, monkeypatch):
    """The definition location returned by request_references must not count as a caller."""
    import slicer.cache as cache_mod
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / ".cache")

    repo = FIXTURES / "fixture_a"
    inv = extract_function_inventory(repo / "lib.py")
    call_idx = build_call_index(repo / "lib.py", inv)

    lsp = _start_lsp(repo)
    with lsp.start_server():
        result = build_call_graph_context(
            [{"file": "lib.py", "key": "helper"}],
            lsp,
            repo,
            inventory_cache={"lib.py": inv},
            call_index_cache={"lib.py": call_idx},
            max_depth=0,
        )

    assert result.get(("lib.py", "helper")) == "full", (
        "helper has 1 real caller so should be 'full', not 'stub'"
    )
    callers_in_result = [k for k in result if k != ("lib.py", "helper")]
    assert ("lib.py", "helper") not in [k for k in callers_in_result], (
        "helper's own definition must not appear as a caller"
    )


def test_flask_decorator_seed_terminates_naturally(tmp_path, monkeypatch):
    """health_check has no static callers — BFS terminates after visiting it alone."""
    import slicer.cache as cache_mod
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / ".cache")

    repo = FIXTURES / "fixture_b"
    lsp = _start_lsp(repo)
    with lsp.start_server():
        result = build_call_graph_context(
            [{"file": "app.py", "key": "health_check"}],
            lsp,
            repo,
            inventory_cache={},
            call_index_cache={},
            max_depth=2,
        )

    assert ("app.py", "health_check") in result
    other_entries = [k for k in result if k != ("app.py", "health_check")]
    assert other_entries == [], (
        f"No callers should be added to frontier; got: {other_entries}"
    )


def test_fan_in_uses_filtered_count_not_raw_refs(tmp_path, monkeypatch):
    """fan_in is counted from real call sites only, not raw LSP references.

    fixture_c/target() is imported (but not called) in importer.py, and
    imported+called in caller.py. Raw non-definition refs = 3 (2 imports + 1 call).
    Only 1 is a real call. With fan_in_threshold=1, target should be 'full'.
    If raw count were used, 3 > 1 would wrongly mark it 'stub'.
    """
    import slicer.cache as cache_mod
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / ".cache")

    repo = FIXTURES / "fixture_c"
    lsp = _start_lsp(repo)
    with lsp.start_server():
        result = build_call_graph_context(
            [{"file": "lib3.py", "key": "target"}],
            lsp,
            repo,
            inventory_cache={},
            call_index_cache={},
            max_depth=1,
            fan_in_threshold=1,
        )

    verdict = result.get(("lib3.py", "target"))
    assert verdict == "full", (
        f"target has 1 real caller (fan_in=1 <= threshold=1), expected 'full', got {verdict!r}"
    )

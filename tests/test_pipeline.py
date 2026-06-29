import textwrap
from pathlib import Path
import pytest
from slicer.cache import load_or_parse
from slicer.pipeline import build_inventory_for_files


def _make_py(tmp_path: Path, name: str, src: str) -> Path:
    f = tmp_path / name
    f.write_text(textwrap.dedent(src), encoding="utf-8")
    return f


def test_parallel_processing_produces_same_result_as_sequential(tmp_path, monkeypatch):
    """build_inventory_for_files 的结果必须与逐个顺序调用 load_or_parse 的结果一致。"""
    import slicer.cache as cache_mod
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / ".cache")

    files = [
        _make_py(tmp_path, "a.py", """\
            def alpha(x: int) -> int:
                \"\"\"Alpha docstring.\"\"\"
                return x + 1
        """),
        _make_py(tmp_path, "b.py", """\
            CONSTANT = 99

            def beta() -> str:
                return "beta"
        """),
        _make_py(tmp_path, "c.py", """\
            class Gamma:
                def delta(self) -> None:
                    pass
        """),
    ]

    sequential = {str(f): load_or_parse(f) for f in files}
    import shutil
    shutil.rmtree(tmp_path / ".cache", ignore_errors=True)

    parallel = build_inventory_for_files(files)

    assert parallel == sequential


def test_empty_file_list_returns_empty_dict():
    result = build_inventory_for_files([])
    assert result == {}


def test_single_file_returns_correct_inventory(tmp_path, monkeypatch):
    import slicer.cache as cache_mod
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / ".cache")

    f = _make_py(tmp_path, "solo.py", """\
        def only_func() -> int:
            return 42
    """)
    result = build_inventory_for_files([f])
    assert str(f) in result
    assert "only_func" in result[str(f)]["functions"]

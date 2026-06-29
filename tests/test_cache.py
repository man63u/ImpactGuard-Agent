import json
from pathlib import Path
import pytest
from slicer.cache import cache_key, load_or_parse, SLICER_VERSION


def test_cache_key_depends_on_content(tmp_path):
    f1 = tmp_path / "a.py"
    f2 = tmp_path / "b.py"
    f1.write_text("def foo(): pass\n", encoding="utf-8")
    f2.write_text("def bar(): pass\n", encoding="utf-8")
    assert cache_key(f1) != cache_key(f2)


def test_load_or_parse_writes_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "sample.py"
    src.write_text("def hello(): pass\n", encoding="utf-8")
    result = load_or_parse(src)
    assert "functions" in result
    assert "module_regions" in result
    cache_dir = tmp_path / ".impactguard_cache"
    assert cache_dir.exists()
    cache_files = list(cache_dir.glob("*.json"))
    assert len(cache_files) == 1
    cached = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert cached == result


def test_cache_invalidated_by_version_bump(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "sample.py"
    src.write_text("def hello(): pass\n", encoding="utf-8")
    import slicer.cache as cache_module
    monkeypatch.setattr(cache_module, "SLICER_VERSION", "v3")
    key_v3 = cache_key(src)
    monkeypatch.setattr(cache_module, "SLICER_VERSION", SLICER_VERSION)
    key_original = cache_key(src)
    assert key_v3 != key_original

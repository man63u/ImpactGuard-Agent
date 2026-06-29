from pathlib import Path
from slicer2.call_graph import uri_to_relpath


def test_uri_to_relpath_inside_root(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    target = repo_root / "lib.py"
    target.write_text("")
    assert uri_to_relpath(target.as_uri(), repo_root) == "lib.py"


def test_uri_to_relpath_outside_root_returns_none(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "elsewhere" / "flask_internals.py"
    outside.parent.mkdir()
    outside.write_text("")
    assert uri_to_relpath(outside.as_uri(), repo_root) is None


def test_uri_to_relpath_nested_path(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "pkg").mkdir(parents=True)
    target = repo_root / "pkg" / "module.py"
    target.write_text("")
    assert uri_to_relpath(target.as_uri(), repo_root) == "pkg/module.py"

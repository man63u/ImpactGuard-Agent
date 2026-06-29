import pytest
import slicer.cache as cache_mod


@pytest.fixture(autouse=False)
def isolated_cache(tmp_path, monkeypatch):
    """Redirect CACHE_DIR to a temp directory."""
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / ".cache")
    yield tmp_path / ".cache"

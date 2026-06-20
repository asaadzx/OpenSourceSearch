import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def temp_cache_file():
    import core.cache as cache_mod
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        f.write("[]")
        tmp = f.name
    old = cache_mod.CACHE_FILE
    cache_mod.CACHE_FILE = tmp
    yield tmp
    cache_mod.CACHE_FILE = old
    try:
        os.unlink(tmp)
    except Exception:
        pass

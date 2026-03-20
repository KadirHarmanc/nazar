"""Tests for cache system."""
import os
from nazar.cache.file_cache import FileCache


def test_cache_init(tmp_path):
    """Cache initializes and creates db."""
    cache = FileCache(str(tmp_path))
    assert os.path.exists(os.path.join(str(tmp_path), "cache.db"))


def test_cache_put_get(tmp_path):
    """Cache stores and retrieves results."""
    cache = FileCache(str(tmp_path))
    test_file = str(tmp_path / "test.py")
    with open(test_file, "w") as f:
        f.write("print('hello')")

    cache.put(test_file, "security", {"passed": True}, cache.hash_file(test_file))
    result = cache.get(test_file, "security", cache.hash_file(test_file))
    assert result is not None
    assert result["passed"] is True


def test_cache_miss_on_change(tmp_path):
    """Cache misses when file changes."""
    cache = FileCache(str(tmp_path))
    test_file = str(tmp_path / "test.py")
    with open(test_file, "w") as f:
        f.write("v1")

    cache.put(test_file, "sec", {"v": 1}, cache.hash_file(test_file))

    with open(test_file, "w") as f:
        f.write("v2")

    result = cache.get(test_file, "sec", cache.hash_file(test_file))
    assert result is None


def test_cache_stats(tmp_path):
    """Cache stats work."""
    cache = FileCache(str(tmp_path))
    stats = cache.stats()
    assert stats["total_entries"] == 0

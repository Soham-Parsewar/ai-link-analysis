"""Unit tests for the thread-safe TTLCache."""

import time
from app.utils.cache import TTLCache


def test_cache_set_and_get():
    """Verify storing and retrieving values."""
    cache = TTLCache(default_ttl=60)
    key = cache.generate_key("https://example.com")
    cache.set(key, {"title": "Example"})

    retrieved = cache.get(key)
    assert retrieved == {"title": "Example"}


def test_cache_expiration():
    """Verify entries expire after TTL."""
    cache = TTLCache(default_ttl=1)  # 1 second
    key = cache.generate_key("https://example.com/expiring")
    cache.set(key, {"data": "temp"}, ttl=1)

    assert cache.get(key) == {"data": "temp"}
    time.sleep(1.1)
    assert cache.get(key) is None


def test_cache_delete_and_clear():
    """Verify cache item deletion and bulk clearing."""
    cache = TTLCache(default_ttl=60)
    k1 = cache.generate_key("https://site1.com")
    k2 = cache.generate_key("https://site2.com")

    cache.set(k1, "data1")
    cache.set(k2, "data2")
    assert cache.size() == 2

    assert cache.delete(k1) is True
    assert cache.get(k1) is None
    assert cache.get(k2) == "data2"
    assert cache.size() == 1

    cache.clear()
    assert cache.size() == 0

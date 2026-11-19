"""Thread-safe in-memory TTL cache for analysis results."""

import hashlib
import time
from threading import Lock
from typing import Any, Optional


class TTLCache:
    """Thread-safe in-memory cache with Time-To-Live (TTL) expiration."""

    def __init__(self, default_ttl: int = 3600):
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = Lock()
        self.default_ttl = default_ttl

    @staticmethod
    def generate_key(url: str, content_hash: Optional[str] = None) -> str:
        """Create a deterministic cache key from the normalized URL and content hash."""
        raw_key = f"{url.strip().lower()}:{content_hash or ''}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Retrieve value if key exists and has not expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            expiry, value = entry
            if time.time() > expiry:
                # Expired
                del self._cache[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store value with expiration timestamp."""
        ttl_seconds = ttl if ttl is not None else self.default_ttl
        expiry = time.time() + ttl_seconds
        with self._lock:
            self._cache[key] = (expiry, value)

    def delete(self, key: str) -> bool:
        """Remove a specific key from the cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Return number of unexpired entries."""
        with self._lock:
            now = time.time()
            return sum(1 for exp, _ in self._cache.values() if exp > now)


# Global cache singleton
analysis_cache = TTLCache()

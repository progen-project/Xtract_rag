"""
cache.py — no-op stubs (Redis removed, caching handled by Nginx proxy_cache).

All cache operations are kept as async no-ops so that any remaining call
sites compile and run without error during a transition period, but they do
nothing at runtime.  Feel free to delete this file and all its imports once
you have verified nothing still references it.
"""


class _NoOpCache:
    """Drop-in replacement for the old ResponseCache that does nothing."""

    async def get(self, key: str):
        return None

    async def set(self, key: str, value, ttl: int = None) -> None:
        return None

    async def invalidate(self, key: str) -> None:
        return None

    async def invalidate_prefix(self, prefix: str) -> int:
        return 0


# Keep the same exported names so existing imports don't break.
category_cache = _NoOpCache()
document_cache = _NoOpCache()
chat_cache = _NoOpCache()
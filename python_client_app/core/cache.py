"""
Redis-backed TTL cache for Client Proxy.

Persists cached responses to Redis for scalability and persistence.
Handles Pydantic model serialization via jsonable_encoder.
"""
import json
import logging
import redis.asyncio as redis
from typing import Any, Optional
from fastapi.encoders import jsonable_encoder
from python_client_app.config import ClientConfig

logger = logging.getLogger(__name__)


class ResponseCache:
    """Async Redis cache for Client Proxy responses."""
    
    def __init__(self, default_ttl: int = 60):
        """
        Args:
            default_ttl: Default time-to-live in seconds.
        """
        self.default_ttl = default_ttl
        self.redis: Optional[redis.Redis] = None
        
    async def _get_redis(self) -> redis.Redis:
        """Lazy initialization of Redis client."""
        if self.redis is None:
            self.redis = redis.from_url(
                ClientConfig.REDIS_URL, 
                encoding="utf-8", 
                decode_responses=True
            )
        return self.redis
    
    async def get(self, key: str) -> Optional[Any]:
        """Get a cached value found by key."""
        try:
            client = await self._get_redis()
            val = await client.get(key)
            return json.loads(val) if val else None
        except Exception as e:
            logger.warning(f"Redis get error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Cache a value with TTL."""
        try:
            client = await self._get_redis()
            expiration = ttl if ttl is not None else self.default_ttl
            
            # Serialize Pydantic models or other types to JSON-compatible dicts
            encoded_value = jsonable_encoder(value)
            json_str = json.dumps(encoded_value)
            
            await client.set(key, json_str, ex=expiration)
        except Exception as e:
            logger.warning(f"Redis set error for key {key}: {e}")
    
    async def invalidate(self, key: str) -> None:
        """Remove a specific cache entry."""
        try:
            client = await self._get_redis()
            await client.delete(key)
        except Exception as e:
            logger.warning(f"Redis invalidate error for key {key}: {e}")
    
    async def invalidate_prefix(self, prefix: str) -> int:
        """Remove all entries starting with prefix."""
        try:
            client = await self._get_redis()
            keys_to_delete = []
            async for k in client.scan_iter(match=f"{prefix}*"):
                keys_to_delete.append(k)
            
            if keys_to_delete:
                await client.delete(*keys_to_delete)
                logger.debug(f"Cache: invalidated {len(keys_to_delete)} keys for prefix '{prefix}'")
                return len(keys_to_delete)
            return 0
        except Exception as e:
            logger.warning(f"Redis invalidate_prefix error for {prefix}: {e}")
            return 0


# Global cache instances
category_cache = ResponseCache(default_ttl=60)   # 1 minutes
document_cache = ResponseCache(default_ttl=60)    # 1 minutes
chat_cache = ResponseCache(default_ttl=60)        # 1 minutes

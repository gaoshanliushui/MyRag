"""
Redis Client

Provides caching and session management:
- Multi-level cache (query, vector, session)
- Async operations with connection pooling
- TTL management
- Cache decorators for functions
"""

import json
import hashlib
from typing import Any, Callable, TypeVar

import redis.asyncio as redis
from redis.asyncio import Redis

from app.config import settings
from app.utils.exceptions import RedisError
from app.utils.logging import get_logger

logger = get_logger("db.redis")

T = TypeVar("T")


class RedisClient:
    """Redis client for caching and session management."""

    def __init__(
        self,
        url: str | None = None,
        db: int | None = None,
    ):
        self.url = url or settings.REDIS_URL
        self.db = db if db is not None else settings.REDIS_CACHE_DB
        self._client: Redis | None = None

    async def connect(self) -> None:
        """Initialize Redis connection."""
        if self._client is None:
            try:
                self._client = redis.from_url(
                    self.url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                logger.info(f"Connected to Redis at {self.url}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise RedisError("connect", str(e))

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Closed Redis connection")

    async def ping(self) -> bool:
        """Check connection."""
        try:
            await self.connect()
            return await self._client.ping()
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False

    def _get_client(self) -> Redis:
        """Get Redis client instance."""
        if self._client is None:
            raise RedisError("get_client", "Client not initialized")
        return self._client

    async def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any | None:
        """
        Get value from cache.

        Returns deserialized JSON or default if not found.
        """
        try:
            client = self._get_client()
            value = await client.get(key)

            if value is None:
                return default

            # Deserialize JSON
            return json.loads(value)

        except Exception as e:
            logger.error(f"Redis get failed for key {key}: {e}")
            return default

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Set value in cache with optional TTL.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds

        Returns True if successful.
        """
        try:
            client = self._get_client()
            serialized = json.dumps(value)

            if ttl:
                await client.setex(key, ttl, serialized)
            else:
                await client.set(key, serialized)

            logger.debug(f"Set key {key} (TTL: {ttl})")
            return True

        except Exception as e:
            logger.error(f"Redis set failed for key {key}: {e}")
            raise RedisError("set", str(e))

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            client = self._get_client()
            await client.delete(key)
            logger.debug(f"Deleted key {key}")
            return True
        except Exception as e:
            logger.error(f"Redis delete failed for key {key}: {e}")
            raise RedisError("delete", str(e))

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        try:
            client = self._get_client()
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                deleted = await client.delete(*keys)
                logger.debug(f"Deleted {deleted} keys matching {pattern}")
                return deleted

            return 0

        except Exception as e:
            logger.error(f"Redis delete_pattern failed: {e}")
            raise RedisError("delete_pattern", str(e))

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        client = self._get_client()
        return await client.exists(key) > 0

    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key."""
        client = self._get_client()
        return await client.expire(key, ttl)

    async def ttl(self, key: str) -> int:
        """Get TTL for key (-1 if no TTL, -2 if not exists)."""
        client = self._get_client()
        return await client.ttl(key)

    async def incr(self, key: str) -> int:
        """Increment counter."""
        client = self._get_client()
        return await client.incr(key)

    async def incrby(self, key: str, amount: int) -> int:
        """Increment by amount."""
        client = self._get_client()
        return await client.incrby(key, amount)

    async def get_json(self, key: str) -> dict[str, Any] | None:
        """Get JSON value directly."""
        client = self._get_client()
        value = await client.get(key)
        if value:
            return json.loads(value)
        return None

    async def set_json(
        self,
        key: str,
        value: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """Set JSON value directly."""
        return await self.set(key, value, ttl)

    # ============================================
    # Multi-Level Cache Operations
    # ============================================

    def _make_cache_key(
        self,
        tenant_id: str,
        cache_type: str,
        *args: Any,
    ) -> str:
        """Generate cache key with tenant isolation."""
        # Hash the arguments for consistent key
        args_hash = hashlib.md5(
            json.dumps(args, sort_keys=True).encode()
        ).hexdigest()[:16]
        return f"{tenant_id}:{cache_type}:{args_hash}"

    async def get_query_cache(
        self,
        tenant_id: str,
        query: str,
        mode: str,
    ) -> dict[str, Any] | None:
        """Get cached query result (L1 cache)."""
        key = self._make_cache_key(tenant_id, "query", query, mode)
        return await self.get_json(key)

    async def set_query_cache(
        self,
        tenant_id: str,
        query: str,
        mode: str,
        result: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """Cache query result."""
        key = self._make_cache_key(tenant_id, "query", query, mode)
        return await self.set_json(key, result, ttl or settings.QUERY_CACHE_TTL)

    async def get_vector_cache(
        self,
        tenant_id: str,
        text_hash: str,
    ) -> list[float] | None:
        """Get cached embedding vector (L2 cache)."""
        key = self._make_cache_key(tenant_id, "vector", text_hash)
        result = await self.get(key)
        if result and isinstance(result, list):
            return result
        return None

    async def set_vector_cache(
        self,
        tenant_id: str,
        text_hash: str,
        embedding: list[float],
        ttl: int | None = None,
    ) -> bool:
        """Cache embedding vector."""
        key = self._make_cache_key(tenant_id, "vector", text_hash)
        return await self.set(key, embedding, ttl or settings.VECTOR_CACHE_TTL)

    async def get_session_cache(
        self,
        tenant_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        """Get session data."""
        key = self._make_cache_key(tenant_id, "session", session_id)
        return await self.get_json(key)

    async def set_session_cache(
        self,
        tenant_id: str,
        session_id: str,
        data: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """Cache session data."""
        key = self._make_cache_key(tenant_id, "session", session_id)
        return await self.set_json(key, data, ttl or settings.SESSION_CACHE_TTL)

    async def delete_tenant_keys(self, tenant_id: str) -> int:
        """
        Delete all Redis keys for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Number of keys deleted
        """
        pattern = f"{tenant_id}:*"
        return await self.delete_pattern(pattern)


# Singleton instance
_redis_client: RedisClient | None = None


async def get_redis_client() -> RedisClient:
    """Get Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
        await _redis_client.connect()
    return _redis_client


# ============================================
# Cache Decorator
# ============================================

def cached(
    tenant_id_arg: str = "tenant_id",
    ttl: int | None = None,
    key_builder: Callable[..., str] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to cache function results.

    Usage:
        @cached(tenant_id_arg="tenant_id", ttl=300)
        async def expensive_function(tenant_id: str, query: str):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Get Redis client
            redis_client = await get_redis_client()

            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Extract tenant_id from kwargs or args
                tenant_id = kwargs.get(tenant_id_arg, "")
                func_name = func.__name__
                args_hash = hashlib.md5(
                    json.dumps((args, kwargs), sort_keys=True).encode()
                ).hexdigest()[:16]
                cache_key = f"{tenant_id}:func:{func_name}:{args_hash}"

            # Try to get from cache
            cached_result = await redis_client.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_result

            # Execute function
            result = await func(*args, **kwargs)

            # Cache result
            await redis_client.set(cache_key, result, ttl)
            logger.debug(f"Cache set for {cache_key}")

            return result

        return wrapper
    return decorator
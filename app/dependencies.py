import hashlib
import json
import logging
import math
from typing import Literal

from fastapi import Depends, HTTPException, Request, Response
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import Settings, get_settings
from app.limiters import BaseLimiter, RateLimitResult, create_limiter
from app.redis_client import get_redis

logger = logging.getLogger("ratelimiter")

Scope = Literal["ip", "client", "global"]


def client_identifier(request: Request, scope: Scope, settings: Settings) -> str:
    """ip     -> caller IP only
    client -> API key (hashed) if sent, otherwise IP
    global -> everyone shares one counter"""
    if scope == "global":
        return "global"

    api_key = request.headers.get("x-api-key")
    if scope == "client" and api_key:
        return "key-" + hashlib.sha256(api_key.encode()).hexdigest()[:16]

    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _headers(limiter: BaseLimiter, result: RateLimitResult, denied: bool) -> dict[str, str]:
    headers = {
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset": str(result.reset_s),
        "X-RateLimit-Algorithm": limiter.name,
    }
    if denied:
        headers["Retry-After"] = str(max(1, result.retry_after_s))
    return headers


class RateLimit:
    """Route-specific rate limit, used as a FastAPI dependency:

        @router.get("/search", dependencies=[Depends(RateLimit("sliding_window_log", 30, 60))])

    Instances are callables, so FastAPI injects Request/Response/Redis/Settings
    into __call__ for every request.
    """

    def __init__(
        self,
        algorithm: str = "token_bucket",
        limit: int = 60,
        window: float = 60,
        *,
        cost: int = 1,
        scope: Scope = "client",
        name: str | None = None,
        **algorithm_options,
    ):
        self.algorithm = algorithm
        self.limit = limit
        self.window = window
        self.cost = cost
        self.scope = scope
        self.name = name
        self.options = algorithm_options
        # build eagerly so a typo in the algorithm name fails at import time, not at 3am
        self.default_limiter = create_limiter(algorithm, limit, window, **algorithm_options)

    @staticmethod
    def _route_name(request: Request) -> str:
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        return f"{request.method}:{path}"

    async def _resolve_limiter(self, redis: Redis, settings: Settings, route_name: str) -> BaseLimiter:
        """Runtime overrides live in a Redis hash, so limits can change without a redeploy."""
        if settings.allow_dynamic_overrides:
            raw = await redis.hget(f"{settings.key_prefix}:config", route_name)
            if raw:
                cfg = json.loads(raw)
                return create_limiter(
                    cfg.get("algorithm", self.algorithm),
                    cfg.get("limit", self.limit),
                    cfg.get("window_seconds", self.window),
                )
        return self.default_limiter

    async def __call__(
        self,
        request: Request,
        response: Response,
        redis: Redis = Depends(get_redis),
        settings: Settings = Depends(get_settings),
    ) -> None:
        route_name = self.name or self._route_name(request)
        identifier = client_identifier(request, self.scope, settings)

        try:
            limiter = await self._resolve_limiter(redis, settings, route_name)
            # {braces} = Redis Cluster hash tag: all keys of one client land in one slot
            key = f"{settings.key_prefix}:{{{identifier}}}:{route_name}:{limiter.name}"
            result = await limiter.hit(redis, key, self.cost)
        except (RedisError, OSError) as exc:
            logger.error("rate limiter backend unavailable: %s", exc)
            if settings.fail_open:
                return
            raise HTTPException(status_code=503, detail="Rate limiter unavailable")

        headers = _headers(limiter, result, denied=not result.allowed)
        if not result.allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "algorithm": limiter.name,
                    "retry_after_seconds": max(1, result.retry_after_s),
                },
                headers=headers,
            )
        for k, v in headers.items():
            response.headers[k] = v

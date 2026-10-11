import redis.asyncio as redis
from fastapi import Request

from app.config import Settings


def create_redis(settings: Settings) -> redis.Redis:
    return redis.from_url(
        settings.redis_url,
        decode_responses=True,
        max_connections=settings.redis_max_connections,
        socket_timeout=settings.redis_timeout,
        socket_connect_timeout=settings.redis_timeout,
        health_check_interval=30,
    )


async def get_redis(request: Request) -> redis.Redis:
    """FastAPI dependency returning the shared client created in the lifespan."""
    return request.app.state.redis

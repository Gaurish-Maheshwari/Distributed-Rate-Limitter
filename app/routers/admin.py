import json
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.config import Settings, get_settings
from app.limiters import Algorithm, create_limiter
from app.redis_client import get_redis


def require_admin(x_admin_key: str = Header(default=""), settings: Settings = Depends(get_settings)):
    if not secrets.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid admin key")


router = APIRouter(prefix="/admin/limits", tags=["admin"], dependencies=[Depends(require_admin)])


class LimitOverride(BaseModel):
    name: str = Field(examples=["GET:/api/fixed-window"], description="'<METHOD>:<route path>' or a custom name")
    algorithm: Algorithm
    limit: int = Field(gt=0)
    window_seconds: float = Field(gt=0)


@router.get("")
async def list_overrides(redis: Redis = Depends(get_redis), settings: Settings = Depends(get_settings)):
    data = await redis.hgetall(f"{settings.key_prefix}:config")
    return {name: json.loads(v) for name, v in data.items()}


@router.put("")
async def set_override(
    body: LimitOverride,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
):
    create_limiter(body.algorithm, body.limit, body.window_seconds)  # validate
    await redis.hset(
        f"{settings.key_prefix}:config",
        body.name,
        json.dumps({"algorithm": body.algorithm, "limit": body.limit, "window_seconds": body.window_seconds}),
    )
    return {"status": "updated", **body.model_dump()}


@router.delete("")
async def delete_override(
    name: str = Query(...),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
):
    removed = await redis.hdel(f"{settings.key_prefix}:config", name)
    return {"status": "deleted" if removed else "not_found", "name": name}

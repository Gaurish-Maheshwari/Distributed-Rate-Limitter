import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from redis.exceptions import RedisError

from app.config import get_settings
from app.limiters.scripts import all_scripts
from app.redis_client import create_redis
from app.routers import admin, demo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ratelimiter")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.redis = create_redis(settings)
    try:  # pre-load scripts so the first request doesn't pay for SCRIPT LOAD
        for script in all_scripts():
            await app.state.redis.script_load(script.source)
        logger.info("Loaded %d Lua scripts", len(all_scripts()))
    except RedisError as exc:
        logger.warning("Redis not reachable at startup (%s); continuing", exc)
    yield
    await app.state.redis.aclose()


app = FastAPI(title="Distributed Rate Limiter", version="1.0.0", lifespan=lifespan)
app.include_router(demo.router)
app.include_router(admin.router)


@app.get("/health", tags=["ops"])
async def health():
    try:
        await app.state.redis.ping()
    except RedisError:
        raise HTTPException(status_code=503, detail="redis unavailable")
    return {"status": "ok"}

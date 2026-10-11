import os
import uuid

import pytest_asyncio
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def redis():
    url = os.getenv("RL_REDIS_URL", "redis://localhost:6379/15")
    client = aioredis.from_url(url, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        import pytest
        pytest.skip(f"Redis not available at {url}")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture
async def client(redis):
    app.state.redis = redis  # ASGITransport does not run lifespan
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
def key():
    return f"test:{{{uuid.uuid4().hex}}}"

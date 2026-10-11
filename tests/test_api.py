async def test_headers_and_429(client):
    codes = []
    for _ in range(6):
        r = await client.get("/api/fixed-window", headers={"X-API-Key": "alice"})
        codes.append(r.status_code)
    assert codes == [200] * 5 + [429]
    assert r.headers["Retry-After"]
    assert r.json()["detail"]["error"] == "rate_limit_exceeded"


async def test_success_headers(client):
    r = await client.get("/api/sliding-log", headers={"X-API-Key": "bob"})
    assert r.status_code == 200
    assert r.headers["X-RateLimit-Limit"] == "5"
    assert r.headers["X-RateLimit-Remaining"] == "4"
    assert r.headers["X-RateLimit-Algorithm"] == "sliding_window_log"


async def test_per_client_isolation(client):
    for _ in range(5):
        await client.get("/api/fixed-window", headers={"X-API-Key": "carol"})
    blocked = await client.get("/api/fixed-window", headers={"X-API-Key": "carol"})
    other = await client.get("/api/fixed-window", headers={"X-API-Key": "dave"})
    assert blocked.status_code == 429
    assert other.status_code == 200


async def test_routes_have_independent_limits(client):
    for _ in range(5):
        await client.get("/api/fixed-window")
    assert (await client.get("/api/fixed-window")).status_code == 429
    assert (await client.get("/api/sliding-log")).status_code == 200


async def test_route_cost(client):
    # limit 20/min, cost 5 -> 4 calls then blocked
    codes = [(await client.get("/api/expensive")).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 200, 429]


async def test_dynamic_override(client):
    admin = {"X-Admin-Key": "change-me"}
    body = {"name": "GET:/api/fixed-window", "algorithm": "fixed_window", "limit": 2, "window_seconds": 60}
    assert (await client.put("/admin/limits", json=body, headers=admin)).status_code == 200
    codes = [(await client.get("/api/fixed-window")).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


async def test_admin_requires_key(client):
    assert (await client.get("/admin/limits")).status_code == 401


async def test_fail_open_when_redis_down(client):
    from app.main import app
    import redis.asyncio as aioredis
    good = app.state.redis
    app.state.redis = aioredis.from_url("redis://localhost:1", socket_connect_timeout=0.1)
    try:
        assert (await client.get("/api/fixed-window")).status_code == 200
    finally:
        app.state.redis = good

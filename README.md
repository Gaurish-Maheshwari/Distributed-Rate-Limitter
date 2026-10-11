# Distributed API Rate Limiter

FastAPI + Redis rate limiter with five algorithms implemented as **atomic Lua scripts**,
applied per-route through FastAPI **dependency injection**, and containerised with Docker.

Because all state lives in Redis (and "now" comes from Redis `TIME`), any number of
stateless API instances enforce one shared limit: no race conditions, no clock skew.

## Project structure

```
rate-limiter/
├── app/
│   ├── main.py                 # app, lifespan (Redis pool + Lua preload), /health
│   ├── config.py               # env-driven settings (RL_* variables)
│   ├── redis_client.py         # async Redis pool + get_redis dependency
│   ├── dependencies.py         # RateLimit: the route-level dependency (headers, 429, fail-open)
│   ├── limiters/
│   │   ├── __init__.py         # algorithm registry + create_limiter()
│   │   ├── base.py             # BaseLimiter, RateLimitResult
│   │   ├── algorithms.py       # 5 thin Python wrappers
│   │   ├── scripts.py          # Lua loader, EVALSHA with EVAL fallback
│   │   └── lua/
│   │       ├── token_bucket.lua
│   │       ├── leaky_bucket.lua
│   │       ├── fixed_window.lua
│   │       ├── sliding_window_log.lua
│   │       └── sliding_window_counter.lua
│   └── routers/
│       ├── demo.py             # one endpoint per algorithm + a weighted-cost endpoint
│       └── admin.py            # change limits at runtime (stored in Redis)
├── tests/                      # needs a real Redis (incl. 100-way concurrency tests)
├── nginx/nginx.conf            # load balancer for the 2-instance demo
├── Dockerfile
├── docker-compose.yml          # redis + api1 + api2 + nginx
├── requirements.txt / requirements-dev.txt
├── pytest.ini
└── .env.example
```

## Run it

```bash
docker compose up --build
# API behind the load balancer: http://localhost:8080   (docs at /docs)

# 7 calls alternate between api1/api2, yet the limit is global
for i in $(seq 7); do curl -s -o /dev/null -w "%{http_code}\n" localhost:8080/api/sliding-log; done
# 200 x5, then 429

curl -i localhost:8080/api/sliding-log     # X-RateLimit-* and Retry-After headers
```

Change a limit live, without redeploying:

```bash
curl -X PUT localhost:8080/admin/limits \
  -H 'X-Admin-Key: change-me' -H 'Content-Type: application/json' \
  -d '{"name":"GET:/api/fixed-window","algorithm":"sliding_window_log","limit":2,"window_seconds":60}'
```

Without Docker: `pip install -r requirements.txt`, start Redis, then
`uvicorn app.main:app --reload`.

## Tests

```bash
docker run -d -p 6379:6379 redis:7-alpine
pip install -r requirements-dev.txt
RL_REDIS_URL=redis://localhost:6379/15 pytest
```

## Using it in your own routes

```python
from fastapi import Depends
from app.dependencies import RateLimit

@app.get("/search", dependencies=[Depends(RateLimit("sliding_window_log", limit=30, window=60))])
async def search(): ...

@app.post("/export", dependencies=[Depends(RateLimit("token_bucket", 20, 60, burst=5, cost=5))])
async def export(): ...

# one counter shared by every caller
Depends(RateLimit("fixed_window", 1000, 60, scope="global", name="site-wide"))
```

`scope`: `client` (API key, else IP; default) · `ip` · `global`.

## Choosing an algorithm

| Algorithm | Memory / client | Accuracy | Bursts | Best for |
|---|---|---|---|---|
| Token bucket | O(1) | exact | up to `burst` | general APIs, bursty clients |
| Leaky bucket | O(1) | exact | smoothed | protecting fragile downstreams |
| Fixed window | O(1) | up to 2x at window edges | edge bursts | cheap, coarse quotas |
| Sliding window log | O(limit) | exact | none | low limits, strict fairness |
| Sliding window counter | O(1) | approximate | minimal | high-traffic default |

## Design notes

- **Atomicity**: the read-modify-write happens inside one Lua script; Redis runs scripts single-threaded.
- **Clock**: scripts use `redis.call('TIME')`, so app servers never disagree about time.
- **EVALSHA** with automatic EVAL fallback; scripts are preloaded at startup.
- **Cleanup**: every key gets a `PEXPIRE`, so idle clients cost nothing.
- **Redis Cluster**: keys carry a `{client}` hash tag, so keys derived inside a script stay in one slot.
- **Failure mode**: `RL_FAIL_OPEN=true` lets traffic through if Redis is down (otherwise 503).
- **Behind a proxy**: set `RL_TRUST_PROXY_HEADERS=true` only if a trusted proxy sets `X-Forwarded-For`.
- If several `RateLimit` dependencies apply to one route, the `X-RateLimit-*` headers come from the last one evaluated.

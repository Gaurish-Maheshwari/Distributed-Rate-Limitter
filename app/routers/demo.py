from fastapi import APIRouter, Depends

from app.dependencies import RateLimit

router = APIRouter(prefix="/api", tags=["demo"])

# A router-wide ceiling shared by every client (scope="global"), on top of per-route limits.
router.dependencies.append(
    Depends(RateLimit("fixed_window", 1000, 60, scope="global", name="api-global"))
)


@router.get("/token-bucket", dependencies=[Depends(RateLimit("token_bucket", 10, 60, burst=5))])
async def token_bucket():
    """Bursts of 5, refills 10/min."""
    return {"algorithm": "token_bucket"}


@router.get("/leaky-bucket", dependencies=[Depends(RateLimit("leaky_bucket", 10, 60, burst=5))])
async def leaky_bucket():
    return {"algorithm": "leaky_bucket"}


@router.get("/fixed-window", dependencies=[Depends(RateLimit("fixed_window", 5, 30))])
async def fixed_window():
    return {"algorithm": "fixed_window"}


@router.get("/sliding-log", dependencies=[Depends(RateLimit("sliding_window_log", 5, 30))])
async def sliding_log():
    return {"algorithm": "sliding_window_log"}


@router.get("/sliding-counter", dependencies=[Depends(RateLimit("sliding_window_counter", 5, 30))])
async def sliding_counter():
    return {"algorithm": "sliding_window_counter"}


@router.get("/expensive", dependencies=[Depends(RateLimit("token_bucket", 20, 60, cost=5))])
async def expensive():
    """Each call consumes 5 tokens, so heavy endpoints burn quota faster."""
    return {"cost": 5}

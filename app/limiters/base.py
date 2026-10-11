import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from redis.asyncio import Redis

from app.limiters.scripts import load_script, run_script


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int           # max requests / burst capacity
    remaining: int
    retry_after_ms: int  # 0 when allowed
    reset_ms: int        # ms until the quota is fully / next replenished

    @property
    def retry_after_s(self) -> int:
        return math.ceil(self.retry_after_ms / 1000)

    @property
    def reset_s(self) -> int:
        return math.ceil(self.reset_ms / 1000)


class BaseLimiter(ABC):
    """One Lua script == one algorithm. Every script returns
    {allowed, remaining, retry_after_ms, reset_ms} and uses Redis TIME so that
    app servers with skewed clocks cannot disagree about "now"."""

    name: ClassVar[str]
    script_file: ClassVar[str]

    def __init__(self, limit: int, window_seconds: float):
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("limit and window_seconds must be > 0")
        self.limit = int(limit)
        self.window_s = float(window_seconds)
        self.window_ms = max(1, int(window_seconds * 1000))

    @property
    def capacity(self) -> int:
        return self.limit

    @abstractmethod
    def build_args(self, cost: int) -> list: ...

    async def hit(self, redis: Redis, key: str, cost: int = 1) -> RateLimitResult:
        raw = await run_script(redis, load_script(self.script_file), [key], self.build_args(cost))
        allowed, remaining, retry_ms, reset_ms = (int(x) for x in raw)
        return RateLimitResult(bool(allowed), self.capacity, remaining, retry_ms, reset_ms)

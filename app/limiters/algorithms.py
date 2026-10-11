import uuid

from app.limiters.base import BaseLimiter


class TokenBucket(BaseLimiter):
    """`limit` tokens are refilled per window; `burst` caps the bucket (default = limit)."""

    name = "token_bucket"
    script_file = "token_bucket.lua"

    def __init__(self, limit: int, window_seconds: float, burst: int | None = None):
        super().__init__(limit, window_seconds)
        self.burst = int(burst or limit)

    @property
    def capacity(self) -> int:
        return self.burst

    def build_args(self, cost: int) -> list:
        return [self.burst, repr(self.limit / self.window_s), cost]


class LeakyBucket(BaseLimiter):
    """Meter-style leaky bucket: requests fill the bucket, it drains at limit/window."""

    name = "leaky_bucket"
    script_file = "leaky_bucket.lua"

    def __init__(self, limit: int, window_seconds: float, burst: int | None = None):
        super().__init__(limit, window_seconds)
        self.burst = int(burst or limit)

    @property
    def capacity(self) -> int:
        return self.burst

    def build_args(self, cost: int) -> list:
        return [self.burst, repr(self.limit / self.window_s), cost]


class FixedWindow(BaseLimiter):
    name = "fixed_window"
    script_file = "fixed_window.lua"

    def build_args(self, cost: int) -> list:
        return [self.limit, self.window_ms, cost]


class SlidingWindowLog(BaseLimiter):
    """Exact, but O(limit) memory per client (one sorted-set member per request)."""

    name = "sliding_window_log"
    script_file = "sliding_window_log.lua"

    def build_args(self, cost: int) -> list:
        return [self.limit, self.window_ms, cost, uuid.uuid4().hex]


class SlidingWindowCounter(BaseLimiter):
    """Weighted blend of the current and previous fixed windows: O(1) memory, ~exact."""

    name = "sliding_window_counter"
    script_file = "sliding_window_counter.lua"

    def build_args(self, cost: int) -> list:
        return [self.limit, self.window_ms, cost]

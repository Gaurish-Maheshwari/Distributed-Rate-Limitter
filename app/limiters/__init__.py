from typing import Literal

from app.limiters.algorithms import (
    FixedWindow,
    LeakyBucket,
    SlidingWindowCounter,
    SlidingWindowLog,
    TokenBucket,
)
from app.limiters.base import BaseLimiter, RateLimitResult

Algorithm = Literal[
    "token_bucket",
    "leaky_bucket",
    "fixed_window",
    "sliding_window_log",
    "sliding_window_counter",
]

ALGORITHMS: dict[str, type[BaseLimiter]] = {
    cls.name: cls
    for cls in (TokenBucket, LeakyBucket, FixedWindow, SlidingWindowLog, SlidingWindowCounter)
}


def create_limiter(algorithm: str, limit: int, window_seconds: float, **options) -> BaseLimiter:
    try:
        cls = ALGORITHMS[algorithm]
    except KeyError:
        raise ValueError(f"Unknown algorithm {algorithm!r}. Choose from {sorted(ALGORITHMS)}")
    return cls(limit, window_seconds, **options)


__all__ = ["Algorithm", "ALGORITHMS", "BaseLimiter", "RateLimitResult", "create_limiter"]

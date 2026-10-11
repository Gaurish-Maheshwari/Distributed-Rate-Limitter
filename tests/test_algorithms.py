import asyncio

import pytest

from app.limiters import ALGORITHMS, create_limiter


@pytest.mark.parametrize("algo", sorted(ALGORITHMS))
async def test_blocks_after_limit(redis, key, algo):
    limiter = create_limiter(algo, 5, 60)
    results = [await limiter.hit(redis, key) for _ in range(7)]
    assert [r.allowed for r in results] == [True] * 5 + [False] * 2
    assert results[0].remaining == 4
    assert results[-1].remaining == 0
    assert results[-1].retry_after_ms > 0


@pytest.mark.parametrize("algo", sorted(ALGORITHMS))
async def test_atomic_under_concurrency(redis, key, algo):
    """100 simultaneous callers must never slip more than `limit` through."""
    limiter = create_limiter(algo, 10, 60)
    results = await asyncio.gather(*(limiter.hit(redis, key) for _ in range(100)))
    assert sum(r.allowed for r in results) == 10


@pytest.mark.parametrize("algo", sorted(ALGORITHMS))
async def test_cost_consumes_multiple_units(redis, key, algo):
    limiter = create_limiter(algo, 10, 60)
    assert (await limiter.hit(redis, key, cost=6)).allowed
    assert not (await limiter.hit(redis, key, cost=6)).allowed
    assert (await limiter.hit(redis, key, cost=4)).allowed


async def test_token_bucket_refills(redis, key):
    limiter = create_limiter("token_bucket", 10, 1)  # 10 tokens/sec
    for _ in range(10):
        assert (await limiter.hit(redis, key)).allowed
    assert not (await limiter.hit(redis, key)).allowed
    await asyncio.sleep(0.35)  # ~3 tokens
    assert (await limiter.hit(redis, key)).allowed


async def test_token_bucket_burst(redis, key):
    limiter = create_limiter("token_bucket", 10, 60, burst=3)
    assert sum([(await limiter.hit(redis, key)).allowed for _ in range(10)]) == 3


async def test_leaky_bucket_drains(redis, key):
    limiter = create_limiter("leaky_bucket", 10, 1)
    for _ in range(10):
        await limiter.hit(redis, key)
    assert not (await limiter.hit(redis, key)).allowed
    await asyncio.sleep(0.25)
    assert (await limiter.hit(redis, key)).allowed


async def test_fixed_window_resets(redis, key):
    limiter = create_limiter("fixed_window", 3, 1)
    for _ in range(3):
        assert (await limiter.hit(redis, key)).allowed
    assert not (await limiter.hit(redis, key)).allowed
    await asyncio.sleep(1.1)
    assert (await limiter.hit(redis, key)).allowed


async def test_sliding_log_has_no_boundary_burst(redis, key):
    """Fixed windows allow 2x limit across a boundary; the sliding log must not."""
    limiter = create_limiter("sliding_window_log", 3, 1)
    for _ in range(3):
        assert (await limiter.hit(redis, key)).allowed
    await asyncio.sleep(0.6)
    assert not (await limiter.hit(redis, key)).allowed   # still inside the 1s window
    await asyncio.sleep(0.5)
    assert (await limiter.hit(redis, key)).allowed       # originals have aged out


async def test_sliding_log_retry_after_is_exact(redis, key):
    limiter = create_limiter("sliding_window_log", 2, 2)
    await limiter.hit(redis, key)
    await limiter.hit(redis, key)
    denied = await limiter.hit(redis, key)
    assert 1500 < denied.retry_after_ms <= 2000


async def test_sliding_counter_blends_previous_window(redis, key):
    import time
    limiter = create_limiter("sliding_window_counter", 10, 1)
    await asyncio.sleep(1 - time.time() % 1 + 0.01)   # align to the start of a window
    for _ in range(10):
        await limiter.hit(redis, key)
    await asyncio.sleep(1.0)  # early in the next window: previous window still weighs ~90%+
    denied = await limiter.hit(redis, key)
    assert not denied.allowed
    assert denied.retry_after_ms > 0
    await asyncio.sleep(1.0)  # two windows later the old traffic no longer counts
    assert (await limiter.hit(redis, key)).allowed


async def test_keys_are_isolated(redis):
    limiter = create_limiter("token_bucket", 1, 60)
    assert (await limiter.hit(redis, "t:{a}")).allowed
    assert (await limiter.hit(redis, "t:{b}")).allowed
    assert not (await limiter.hit(redis, "t:{a}")).allowed


def test_invalid_algorithm():
    with pytest.raises(ValueError):
        create_limiter("nope", 1, 1)

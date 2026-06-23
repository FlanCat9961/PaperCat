import pytest

from papercat.core.sources.ratelimit import TokenBucket


@pytest.mark.asyncio
async def test_first_acquire_does_not_sleep() -> None:
    sleeps = []
    bucket = TokenBucket(1.0, clock=lambda: 10.0, sleeper=lambda delay: record_sleep(sleeps, delay))

    await bucket.acquire()

    assert sleeps == []


@pytest.mark.asyncio
async def test_second_acquire_sleeps_remaining_time() -> None:
    times = iter([10.0, 10.25, 11.0])
    sleeps = []
    bucket = TokenBucket(
        1.0, clock=lambda: next(times), sleeper=lambda delay: record_sleep(sleeps, delay)
    )

    await bucket.acquire()
    await bucket.acquire()

    assert sleeps == [pytest.approx(0.75)]


async def record_sleep(sleeps: list[float], delay: float) -> None:
    sleeps.append(delay)

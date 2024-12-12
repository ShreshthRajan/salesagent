import pytest
import asyncio
from src.utils.rate_limiter import RateLimiter

@pytest.mark.asyncio
async def test_rate_limiter():
    limiter = RateLimiter(requests_per_minute=60)

    async def dummy_task():
        return True

    result = await limiter.execute("test", dummy_task)
    assert result is True

@pytest.mark.asyncio
async def test_rate_limiter_throttling():
    limiter = RateLimiter(requests_per_minute=2)
    results = []

    async def dummy_task():
        results.append(asyncio.get_event_loop().time())
        return True

    # Execute 3 tasks in quick succession
    await asyncio.gather(
        limiter.execute("test", dummy_task),
        limiter.execute("test", dummy_task),
        limiter.execute("test", dummy_task)
    )

    # Check that the time difference between first and last execution is at least 1 second
    assert results[-1] - results[0] >= 1.0
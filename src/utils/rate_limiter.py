from datetime import datetime, timedelta
import asyncio
from collections import defaultdict
from typing import Dict, List
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, requests_per_minute: int, max_concurrent: int = 1):
        self.rate_limit = requests_per_minute
        self.window_size = 60  # seconds
        self.max_concurrent = max_concurrent
        self.requests: Dict[str, List[datetime]] = defaultdict(list)
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def acquire(self, key: str = "default"):
        """Acquire rate limit permission"""
        while True:
            now = datetime.now()
            window_start = now - timedelta(seconds=self.window_size)

            # Clean old requests
            self.requests[key] = [ts for ts in self.requests[key] if ts > window_start]

            if len(self.requests[key]) < self.rate_limit:
                self.requests[key].append(now)
                break

            # Wait until oldest request expires
            wait_time = (self.requests[key][0] - window_start).total_seconds()
            await asyncio.sleep(wait_time)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def execute(self, key: str, func, *args, **kwargs):
        """Execute function with rate limiting"""
        async with self.semaphore:
            await self.acquire(key)
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error executing rate-limited function: {e}")
                raise
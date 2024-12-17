from typing import Any, Dict, Optional
from unittest.mock import AsyncMock

class MockHTTPResponse:
    """Mock HTTP Response with proper async support"""
    def __init__(self, data: Dict[str, Any], status: int = 200):
        self.data = data
        self._status = status

    async def json(self):
        return self.data

    @property
    def status(self):
        return self._status

class AsyncContextManagerMock:
    """Helper for mocking async context managers"""
    def __init__(self, response: MockHTTPResponse):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

class MockAioHTTPClient:
    """Mock aiohttp client with proper async context manager support"""
    def __init__(self, responses: Dict[str, MockHTTPResponse]):
        self.responses = responses
        self.calls = []

    def get(self, url: str, *args, **kwargs) -> AsyncContextManagerMock:
        self.calls.append((url, args, kwargs))
        # Find the matching response based on URL
        for pattern, response in self.responses.items():
            if pattern in url:
                return AsyncContextManagerMock(response)
        # Return empty response if no match
        return AsyncContextManagerMock(MockHTTPResponse({}, 404))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
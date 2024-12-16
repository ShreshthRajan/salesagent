import pytest_asyncio
import os
from dotenv import load_dotenv
from src.services.browser_manager import BrowserPool
from src.services.browser_context import BrowserSession

# Load environment variables at the start of testing
load_dotenv()

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_env():
    """Setup test environment with required env vars if not present"""
    test_keys = {
        'APOLLO_API_KEY': 'test_apollo_key',
        'ROCKETREACH_API_KEY': 'test_rocketreach_key',
        'OPENAI_API_KEY': 'test_openai_key'
    }
    
    for key, value in test_keys.items():
        if not os.getenv(key):
            os.environ[key] = value

@pytest_asyncio.fixture(scope="function")
async def browser_pool():
    """Provides initialized browser pool for testing"""
    pool = BrowserPool()
    # Disable proxy warnings for tests
    pool.proxy_manager.get_proxy = lambda: None  # Mock the get_proxy method
    await pool.initialize()
    pool.use_proxy = False
    yield pool
    await pool.cleanup()

@pytest_asyncio.fixture(scope="function")
async def browser_context(browser_pool):
    """Provides browser context"""
    context = await browser_pool.get_context()
    yield context
    await browser_pool.cleanup_context(context)

@pytest_asyncio.fixture(scope="function")
async def browser_session(browser_context):
    """Provides browser session"""
    session = BrowserSession(browser_context)
    async with session as s:
        yield s
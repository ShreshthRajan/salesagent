import pytest_asyncio
import os
from dotenv import load_dotenv
from src.services.browser_manager import BrowserPool
from src.services.browser_context import BrowserSession
from src.utils.config import ConfigManager
import logging
import pytest

logger = logging.getLogger(__name__)

# Load environment variables at the start of testing
load_dotenv()

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_env():
    """Load environment and config, but do NOT raise if a key is invalid."""
    manager = ConfigManager()
    try:
        # Just load config & set up env
        await manager.initialize()
    except Exception as e:
        logger.warning(f"Something went wrong, but continuing: {e}")
    # Do not raise or skip
    return manager

@pytest_asyncio.fixture
async def config_manager():
    """Fixture that returns the manager object, 
       but does *not* forcibly validate Apollo & RR every time."""
    manager = ConfigManager()
    await manager.initialize()
    return manager


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
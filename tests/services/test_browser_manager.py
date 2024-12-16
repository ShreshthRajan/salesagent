import pytest
from playwright.async_api import BrowserContext
from src.services.browser_manager import BrowserPool
from src.utils.exceptions import BrowserException

@pytest.mark.asyncio
async def test_browser_initialization(browser_pool):
    """Test browser pool initialization"""
    assert browser_pool._playwright is not None
    assert isinstance(browser_pool.browsers, dict)

@pytest.mark.asyncio
async def test_context_creation(browser_pool):
    """Test browser context creation"""
    context = await browser_pool.get_context()
    assert isinstance(context, BrowserContext)
    await browser_pool.cleanup_context(context)

@pytest.mark.asyncio
async def test_multiple_contexts(browser_pool):
    """Test multiple context creation"""
    contexts = []
    for _ in range(3):
        context = await browser_pool.get_context()
        contexts.append(context)
    
    assert len(contexts) == 3
    for context in contexts:
        await browser_pool.cleanup_context(context)

@pytest.mark.asyncio
async def test_browser_cleanup(browser_pool):
    """Test cleanup functionality"""
    context = await browser_pool.get_context()
    await browser_pool.cleanup()
    assert len(browser_pool.browsers) == 0
    assert len(browser_pool.contexts) == 0
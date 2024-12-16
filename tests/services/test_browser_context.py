import pytest
from playwright.async_api import Page
from src.utils.exceptions import NavigationError

@pytest.mark.asyncio
async def test_session_creation(browser_session):
    """Test session initialization"""
    assert browser_session.page is not None
    assert isinstance(browser_session.page, Page)

@pytest.mark.asyncio
async def test_navigation(browser_session):
    """Test navigation functionality"""
    await browser_session.navigate("https://example.com")
    assert "example.com" in browser_session.page.url

@pytest.mark.asyncio
async def test_storage_state(browser_session):
    """Test storage state management"""
    await browser_session.navigate("https://example.com")
    await browser_session.save_storage_state()
    await browser_session.restore_storage_state()
    await browser_session.clear_storage()
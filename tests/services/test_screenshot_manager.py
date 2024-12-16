import pytest
from pathlib import Path
from src.services.screenshot_manager import ScreenshotManager
from src.utils.exceptions import ScreenshotError

@pytest.mark.asyncio
async def test_screenshot_capture(browser_session):
    """Test screenshot capture"""
    manager = ScreenshotManager(browser_session.page)
    await browser_session.navigate("https://example.com")
    
    filepath = await manager.capture("test")
    assert filepath.exists()
    filepath.unlink()  # Cleanup

@pytest.mark.asyncio
async def test_error_screenshot(browser_session):
    """Test error screenshot capture"""
    manager = ScreenshotManager(browser_session.page)
    await browser_session.navigate("https://example.com")
    
    filepath = await manager.capture_error("Test error")
    context_file = filepath.parent / f"{filepath.stem}_context.txt"
    
    assert filepath.exists()
    assert context_file.exists()
    
    # Cleanup
    filepath.unlink()
    context_file.unlink()

@pytest.mark.asyncio
async def test_screenshot_cleanup(browser_session):
    """Test screenshot cleanup"""
    manager = ScreenshotManager(browser_session.page)
    await browser_session.navigate("https://example.com")
    
    # Create a test screenshot
    filepath = await manager.capture("test")
    assert filepath.exists()
    
    # Test cleanup
    manager.cleanup_old_screenshots(max_age_days=0)
    assert not filepath.exists()
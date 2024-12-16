import pytest
from src.services.element_handler import ElementHandler
from src.utils.exceptions import ElementNotFoundException, ElementInteractionError

@pytest.mark.asyncio
async def test_click_element(browser_session):
    """Test element clicking"""
    handler = ElementHandler(browser_session.page)
    await browser_session.navigate("https://example.com")
    await handler.click("body")

@pytest.mark.asyncio
async def test_type_text(browser_session):
    """Test text input"""
    handler = ElementHandler(browser_session.page)
    await browser_session.navigate("https://example.com")
    
    # Should raise error for non-existent element
    with pytest.raises(ElementInteractionError):
        await handler.type_text("#nonexistent", "test text")

@pytest.mark.asyncio
async def test_wait_for_element(browser_session):
    """Test element waiting"""
    handler = ElementHandler(browser_session.page)
    await browser_session.navigate("https://example.com")
    
    # Should find the body element
    element = await handler.wait_for_element("body")
    assert element is not None
    
    # Should timeout for non-existent element
    with pytest.raises(ElementNotFoundException):  # Changed from TimeoutError to ElementNotFoundException
        await handler.wait_for_element("#nonexistent", timeout=1000)

@pytest.mark.asyncio
async def test_element_visibility(browser_session):
    """Test element visibility check"""
    handler = ElementHandler(browser_session.page)
    await browser_session.navigate("https://example.com")
    
    assert await handler.is_visible("body") is True
    assert await handler.is_visible("#nonexistent") is False
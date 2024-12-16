import asyncio
from typing import Optional, Any, List
import logging
from playwright.async_api import Page, ElementHandle, TimeoutError as PlaywrightTimeoutError
from src.utils.exceptions import (
    ElementNotFoundException, ElementInteractionError, TimeoutError
)
from src.utils.config import ConfigManager

logger = logging.getLogger(__name__)

class ElementHandler:
    """Handles element interactions and operations"""
    
    def __init__(self, page: Page):
        self.page = page
        self.config = ConfigManager().config
        self.timeout = self.config.browser.timeout

    async def click(self, selector: str, timeout: Optional[int] = None) -> None:
        """Click an element with retries"""
        try:
            await self.page.click(
                selector,
                timeout=timeout or self.timeout,
                retry_intervals=[100, 250, 500]  # Progressive retry intervals
            )
            logger.debug(f"Clicked element: {selector}")
        except PlaywrightTimeoutError:
            raise TimeoutError("click", timeout or self.timeout, f"Click operation timed out for selector: {selector}")
        except Exception as e:
            raise ElementInteractionError(selector, "click", str(e))

    async def type_text(self, selector: str, text: str, delay: int = 50) -> None:
        """Type text into an element"""
        try:
            await self.page.type(selector, text, delay=delay)
            logger.debug(f"Typed text into element: {selector}")
        except Exception as e:
            raise ElementInteractionError(selector, "type", str(e))

    async def wait_for_element(self, selector: str, timeout: Optional[int] = None) -> ElementHandle:
        """Wait for an element to be present"""
        try:
            element = await self.page.wait_for_selector(
                selector,
                timeout=timeout or self.timeout,
                state="visible"
            )
            if not element:
                raise ElementNotFoundException(selector)
            return element
        except PlaywrightTimeoutError:
            raise TimeoutError(
                "wait_for_element",
                timeout or self.timeout,
                f"Timeout waiting for element: {selector}"
            )
        except Exception as e:
            raise ElementNotFoundException(selector, str(e))

    async def get_text(self, selector: str) -> str:
        """Get text content of an element"""
        try:
            element = await self.wait_for_element(selector)
            text = await element.text_content()
            return text.strip() if text else ""
        except Exception as e:
            raise ElementInteractionError(selector, "get_text", str(e))

    async def wait_for_navigation(self, timeout: Optional[int] = None) -> None:
        """Wait for navigation to complete"""
        try:
            await self.page.wait_for_load_state(
                "networkidle",
                timeout=timeout or self.timeout
            )
        except PlaywrightTimeoutError:
            raise TimeoutError(
                "navigation",
                timeout or self.timeout,
                "Navigation timeout"
            )

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        """Evaluate JavaScript in the page context"""
        try:
            return await self.page.evaluate(script, arg)
        except Exception as e:
            raise ElementInteractionError("script", "evaluate", str(e))

    async def select_option(self, selector: str, value: str) -> None:
        """Select an option from a dropdown"""
        try:
            await self.page.select_option(selector, value)
            logger.debug(f"Selected option {value} in {selector}")
        except Exception as e:
            raise ElementInteractionError(selector, "select", str(e))

    async def is_visible(self, selector: str) -> bool:
        """Check if an element is visible"""
        try:
            element = await self.page.query_selector(selector)
            if not element:
                return False
            return await element.is_visible()
        except Exception:
            return False
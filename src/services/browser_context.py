from typing import Optional, Dict, Any
import logging
from playwright.async_api import BrowserContext, Page
from src.utils.exceptions import NavigationError, SessionError, TimeoutError
from src.utils.config import ConfigManager

logger = logging.getLogger(__name__)

class BrowserSession:
    """Manages a browser session with context and page management"""
    
    def __init__(self, context: BrowserContext):
        self.config = ConfigManager().config
        self.context = context
        self.page: Optional[Page] = None
        self._storage_state: Dict[str, Any] = {}

    async def __aenter__(self):
        """Context manager entry"""
        try:
            self.page = await self.context.new_page()
            return self
        except Exception as e:
            raise SessionError(message=f"Failed to create page: {str(e)}")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        try:
            if self.page:
                await self.page.close()
        except Exception as e:
            logger.error(f"Error closing page: {str(e)}")

    async def navigate(self, url: str, wait_until: str = 'networkidle'):
        """Navigate to a URL and wait for loading"""
        try:
            response = await self.page.goto(
                url,
                wait_until=wait_until,
                timeout=self.config.browser.timeout
            )
            
            if not response or not response.ok:
                raise NavigationError(
                    url,
                    f"Navigation failed with status: {response.status if response else 'No response'}"
                )

            logger.info(f"Successfully navigated to {url}")
            return response

        except TimeoutError:
            raise TimeoutError("navigation", self.config.browser.timeout, f"Navigation to {url} timed out")
        except Exception as e:
            raise NavigationError(url, str(e))

    async def save_storage_state(self):
        """Save the current storage state"""
        try:
            self._storage_state = await self.context.storage_state()
        except Exception as e:
            raise SessionError(message=f"Failed to save storage state: {str(e)}")

    async def restore_storage_state(self):
        """Restore the saved storage state"""
        try:
            if self._storage_state:
                await self.context.add_cookies(self._storage_state.get('cookies', []))
                logger.info("Restored storage state")
        except Exception as e:
            raise SessionError(message=f"Failed to restore storage state: {str(e)}")

    async def clear_storage(self):
        """Clear browser storage"""
        try:
            await self.context.clear_cookies()
            if self.page:
                await self.page.evaluate("localStorage.clear()")
                await self.page.evaluate("sessionStorage.clear()")
            self._storage_state = {}
            logger.info("Cleared browser storage")
        except Exception as e:
            raise SessionError(message=f"Failed to clear storage: {str(e)}")
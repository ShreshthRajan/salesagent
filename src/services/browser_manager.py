import asyncio
from typing import Dict, Optional, List
import logging
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from src.utils.config import ConfigManager
from src.utils.proxies import ProxyManager
from src.utils.exceptions import (
    BrowserException, BrowserPoolError, SessionError, ProxyConnectionError
)

logger = logging.getLogger(__name__)

class BrowserPool:
    """Manages a pool of browser instances"""
    def __init__(self):
        self.config = ConfigManager().config
        self.proxy_manager = ProxyManager(
            rotation_interval=self.config.proxies.rotation_interval,
            max_failures=self.config.proxies.max_failures
        )
        self.browsers: Dict[str, Browser] = {}
        self.contexts: Dict[str, List[BrowserContext]] = {}
        self.semaphore = asyncio.Semaphore(self.config.browser.max_concurrent)
        self._playwright = None

    async def initialize(self):
        """Initialize the browser pool"""
        try:
            self._playwright = await async_playwright().start()
            logger.info("Initialized playwright")
        except Exception as e:
            raise BrowserException(f"Failed to initialize playwright: {str(e)}")

    async def get_context(self, browser_id: str = "default") -> BrowserContext:
        """Get or create a browser context"""
        async with self.semaphore:
            try:
                if browser_id not in self.browsers:
                    await self._create_browser(browser_id)

                context = await self._create_context(browser_id)
                return context

            except Exception as e:
                raise SessionError(f"Failed to get browser context: {str(e)}")

    async def _create_browser(self, browser_id: str):
        """Create a new browser instance"""
        try:
            self.browsers[browser_id] = await self._playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            self.contexts[browser_id] = []
            logger.info(f"Created new browser instance: {browser_id}")
        except Exception as e:
            raise BrowserPoolError(f"Failed to create browser: {str(e)}")

    async def _create_context(self, browser_id: str) -> BrowserContext:
        """Create a new browser context with proxy"""
        try:
            proxy = self.proxy_manager.get_proxy()
            proxy_config = None
            
            if proxy:
                proxy_config = {
                    "server": f"socks5://{proxy.host}:{proxy.port}",
                    "username": proxy.username,
                    "password": proxy.password
                } if proxy.username and proxy.password else {
                    "server": f"socks5://{proxy.host}:{proxy.port}"
                }

            context = await self.browsers[browser_id].new_context(
                proxy=proxy_config,
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )

            self.contexts[browser_id].append(context)
            return context

        except Exception as e:
            if proxy:
                self.proxy_manager.mark_failed(proxy)
            raise ProxyConnectionError(
                proxy.host if proxy else "No proxy", 
                f"Failed to create context: {str(e)}"
            )

    async def cleanup_context(self, context: BrowserContext):
        """Clean up a browser context"""
        try:
            await context.close()
            for browser_id, contexts in self.contexts.items():
                if context in contexts:
                    contexts.remove(context)
                    logger.info(f"Cleaned up browser context for {browser_id}")
                    break
        except Exception as e:
            logger.error(f"Error cleaning up context: {str(e)}")

    async def cleanup(self):
        """Clean up all browser instances and contexts"""
        try:
            for browser_id, browser in self.browsers.items():
                for context in self.contexts[browser_id]:
                    await context.close()
                await browser.close()
                logger.info(f"Cleaned up browser: {browser_id}")
            
            if self._playwright:
                await self._playwright.stop()
                logger.info("Stopped playwright")

            self.browsers.clear()
            self.contexts.clear()
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            raise BrowserException(f"Failed to cleanup browser pool: {str(e)}")
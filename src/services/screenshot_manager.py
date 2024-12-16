from datetime import datetime
import os
from pathlib import Path
import logging
from typing import Optional
from playwright.async_api import Page
from src.utils.exceptions import ScreenshotError
from src.utils.config import ConfigManager

logger = logging.getLogger(__name__)

class ScreenshotManager:
    """Manages screenshot capture and storage"""

    def __init__(self, page: Page):
        self.page = page
        self.config = ConfigManager().config
        self.screenshot_dir = Path("logs/screenshots")
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Ensure screenshot directory exists"""
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def _generate_filename(self, prefix: str = "screenshot") -> str:
        """Generate unique filename for screenshot"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{prefix}_{timestamp}.png"

    async def capture(
        self,
        name: Optional[str] = None,
        full_page: bool = True,
        element_selector: Optional[str] = None
    ) -> Path:
        """Capture a screenshot"""
        try:
            filename = self._generate_filename(name or "screenshot")
            filepath = self.screenshot_dir / filename

            if element_selector:
                element = await self.page.query_selector(element_selector)
                if not element:
                    raise ScreenshotError(message=f"Element not found: {element_selector}")
                await element.screenshot(path=str(filepath))
            else:
                await self.page.screenshot(
                    path=str(filepath),
                    full_page=full_page
                )

            logger.info(f"Captured screenshot: {filename}")
            return filepath

        except Exception as e:
            raise ScreenshotError(message=f"Failed to capture screenshot: {str(e)}")

    async def capture_error(self, error_message: str) -> Path:
        """Capture screenshot for error state"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"error_{timestamp}.png"
            filepath = self.screenshot_dir / filename

            await self.page.screenshot(path=str(filepath), full_page=True)
            
            # Save error context
            context_file = self.screenshot_dir / f"error_{timestamp}_context.txt"
            with open(context_file, 'w') as f:
                f.write(f"Error: {error_message}\n")
                f.write(f"URL: {self.page.url}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")

            logger.error(f"Error screenshot captured: {filename}")
            return filepath

        except Exception as e:
            raise ScreenshotError(message=f"Failed to capture error screenshot: {str(e)}")

    def cleanup_old_screenshots(self, max_age_days: int = 7) -> None:
        """Clean up screenshots older than specified days"""
        try:
            current_time = datetime.now().timestamp()
            max_age_seconds = max_age_days * 24 * 60 * 60

            for file in self.screenshot_dir.glob("*.png"):
                if current_time - file.stat().st_mtime > max_age_seconds:
                    file.unlink()
                    logger.info(f"Deleted old screenshot: {file.name}")

            # Clean up corresponding context files
            for file in self.screenshot_dir.glob("*_context.txt"):
                if current_time - file.stat().st_mtime > max_age_seconds:
                    file.unlink()

        except Exception as e:
            logger.error(f"Failed to cleanup screenshots: {str(e)}")
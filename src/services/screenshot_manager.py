# src/services/screenshot_manager.py
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from playwright.async_api import Page
from PIL import Image
import io
from src.utils.exceptions import ScreenshotError
from src.utils.config import ConfigManager

logger = logging.getLogger(__name__)

class ScreenshotManager:
    """Enhanced screenshot manager with fast capture pipeline"""
    
    def __init__(self, page: Page):
        self.page = page
        self.config = ConfigManager().config
        self.screenshot_dir = Path("logs/screenshots")
        self.cache_dir = Path("cache/screenshots")
        self._ensure_directories()
        self.semaphore = asyncio.Semaphore(3)  # Limit concurrent captures
        self.compression_quality = 85
        self.max_dimension = 1920

    def _ensure_directories(self) -> None:
        """Ensure required directories exist"""
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _generate_filename(self, prefix: str = "screenshot") -> str:
        """Generate unique filename for screenshot"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{prefix}_{timestamp}.png"

    async def capture(
        self,
        name: Optional[str] = None,
        full_page: bool = True,
        element_selector: Optional[str] = None,
        optimize: bool = True
    ) -> Path:
        """Enhanced screenshot capture with optimization"""
        async with self.semaphore:
            try:
                filename = self._generate_filename(name or "screenshot")
                filepath = self.screenshot_dir / filename

                if element_selector:
                    element = await self.page.query_selector(element_selector)
                    if not element:
                        raise ScreenshotError(f"Element not found: {element_selector}")
                    await element.screenshot(path=str(filepath))
                else:
                    await self.page.screenshot(
                        path=str(filepath),
                        full_page=full_page
                    )

                logger.info(f"Captured screenshot: {filename}")

                if optimize:
                    return await self._optimize_screenshot(filepath)
                return filepath

            except Exception as e:
                raise ScreenshotError(f"Failed to capture screenshot: {str(e)}")

    async def capture_multiple(
        self,
        selectors: List[str],
        base_name: str = "multi"
    ) -> List[Path]:
        """Capture multiple screenshots in parallel"""
        tasks = []
        for i, selector in enumerate(selectors):
            task = asyncio.create_task(
                self.capture(
                    name=f"{base_name}_{i}",
                    element_selector=selector,
                    optimize=True
                )
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_screenshots = [
            result for result in results
            if not isinstance(result, Exception)
        ]

        return valid_screenshots

    async def _optimize_screenshot(self, filepath: Path) -> Path:
        """Optimize screenshot for size and quality"""
        try:
            cache_path = self.cache_dir / f"opt_{filepath.name}"
            
            if cache_path.exists():
                return cache_path

            # Run optimization in thread pool
            loop = asyncio.get_event_loop()
            optimized_path = await loop.run_in_executor(
                None,
                self._optimize_image,
                filepath,
                cache_path
            )

            return optimized_path

        except Exception as e:
            logger.error(f"Screenshot optimization failed: {str(e)}")
            return filepath

    def _optimize_image(self, input_path: Path, output_path: Path) -> Path:
        """Optimize image in separate thread"""
        with Image.open(input_path) as img:
            # Resize if needed
            if max(img.size) > self.max_dimension:
                ratio = self.max_dimension / max(img.size)
                new_size = tuple(int(dim * ratio) for dim in img.size)
                img = img.resize(new_size, Image.LANCZOS)

            # Optimize and save
            img.save(
                output_path,
                "PNG",
                optimize=True,
                quality=self.compression_quality
            )

        return output_path

    async def capture_error(self, error_message: str) -> Path:
        """Capture screenshot for error state with optimization"""
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
            return await self._optimize_screenshot(filepath)

        except Exception as e:
            raise ScreenshotError(f"Failed to capture error screenshot: {str(e)}")

    async def cleanup_old_screenshots(self, max_age_days: int = 7) -> None:
        """Clean up old screenshots and cache"""
        try:
            current_time = datetime.now().timestamp()
            max_age_seconds = max_age_days * 24 * 60 * 60

            # Clean up screenshots
            for directory in [self.screenshot_dir, self.cache_dir]:
                for file in directory.glob("*.png"):
                    if current_time - file.stat().st_mtime > max_age_seconds:
                        file.unlink()
                        logger.info(f"Deleted old file: {file.name}")

            # Clean up context files
            for file in self.screenshot_dir.glob("*_context.txt"):
                if current_time - file.stat().st_mtime > max_age_seconds:
                    file.unlink()

        except Exception as e:
            logger.error(f"Failed to cleanup screenshots: {str(e)}")

    async def get_screenshot_metrics(self) -> Dict:
        """Get screenshot manager metrics"""
        try:
            screenshots = list(self.screenshot_dir.glob("*.png"))
            cache_files = list(self.cache_dir.glob("*.png"))
            
            return {
                'screenshot_count': len(screenshots),
                'cache_count': len(cache_files),
                'total_size_mb': sum(f.stat().st_size for f in screenshots + cache_files) / (1024 * 1024),
                'optimization_ratio': self._calculate_optimization_ratio()
            }
        except Exception as e:
            logger.error(f"Failed to get metrics: {str(e)}")
            return {}
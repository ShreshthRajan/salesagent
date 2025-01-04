# src/services/screenshot_pipeline.py
from typing import Optional, List, Dict
import logging
from pathlib import Path
import asyncio
from PIL import Image
import io
import hashlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from src.utils.exceptions import ScreenshotError
from src.services.screenshot_manager import ScreenshotManager

logger = logging.getLogger(__name__)


class ScreenshotPipeline:
    """Enhanced screenshot pipeline with optimization and parallel processing"""
    
    def __init__(self, screenshot_manager: ScreenshotManager):
        self.screenshot_manager = screenshot_manager
        self.cache_dir = Path("cache/screenshots")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
        self.compression_quality = 85
        self.max_dimension = 1920
        self.cleanup_threshold = 1000  # Number of files before cleanup
        self.pending_tasks: List[asyncio.Task] = []

    async def capture_optimized(
        self,
        name: Optional[str] = None,
        full_page: bool = True,
        element_selector: Optional[str] = None,
        optimize: bool = True
    ) -> Path:
        """Capture and optimize screenshot"""
        try:
            # Capture screenshot
            screenshot_path = await self.screenshot_manager.capture(
                name=name,
                full_page=full_page,
                element_selector=element_selector
            )
            
            if optimize:
                # Optimize in thread pool
                optimized_path = await self._optimize_screenshot(screenshot_path)
                return optimized_path
            
            return screenshot_path

        except Exception as e:
            raise ScreenshotError(f"Failed to capture optimized screenshot: {str(e)}")

    async def capture_parallel(
        self,
        selectors: List[str],
        base_name: str
    ) -> List[Path]:
        """Capture multiple screenshots in parallel"""
        tasks = []
        for i, selector in enumerate(selectors):
            task = asyncio.create_task(
                self.capture_optimized(
                    name=f"{base_name}_{i}",
                    element_selector=selector
                )
            )
            tasks.append(task)
            self.pending_tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Clean up completed tasks
        self.pending_tasks = [t for t in self.pending_tasks if not t.done()]
        
        # Filter out errors
        valid_screenshots = [
            result for result in results
            if not isinstance(result, Exception)
        ]
        
        return valid_screenshots

    async def _optimize_screenshot(self, screenshot_path: Path) -> Path:
        """Optimize screenshot for size and quality"""
        try:
            # Generate cache key
            cache_key = self._generate_cache_key(screenshot_path)
            cached_path = self.cache_dir / f"{cache_key}.png"
            
            if cached_path.exists():
                return cached_path
            
            # Optimize in thread pool
            loop = asyncio.get_event_loop()
            optimized_path = await loop.run_in_executor(
                self.thread_pool,
                self._optimize_image,
                screenshot_path,
                cached_path
            )
            
            return optimized_path

        except Exception as e:
            logger.error(f"Screenshot optimization failed: {str(e)}")
            return screenshot_path

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

    def _generate_cache_key(self, path: Path) -> str:
        """Generate cache key from file content"""
        with open(path, 'rb') as f:
            content = f.read()
        return hashlib.md5(content).hexdigest()

    async def batch_process(self, screenshot_paths: List[Path]) -> List[Path]:
        """Process multiple screenshots in batch"""
        try:
            tasks = []
            for path in screenshot_paths:
                task = asyncio.create_task(self._optimize_screenshot(path))
                tasks.append(task)
                self.pending_tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Clean up completed tasks
            self.pending_tasks = [t for t in self.pending_tasks if not t.done()]
            
            # Filter out errors
            valid_results = [
                result for result in results
                if not isinstance(result, Exception)
            ]
            
            return valid_results
            
        except Exception as e:
            logger.error(f"Batch processing failed: {str(e)}")
            return []

    async def capture_sequence(
        self,
        selectors: List[str],
        delay: float = 0.5,
        base_name: str = "sequence"
    ) -> List[Path]:
        """Capture sequence of screenshots with delay"""
        screenshots = []
        for i, selector in enumerate(selectors):
            try:
                screenshot = await self.capture_optimized(
                    name=f"{base_name}_{i}",
                    element_selector=selector
                )
                screenshots.append(screenshot)
                await asyncio.sleep(delay)
            except Exception as e:
                logger.error(f"Sequence capture failed at step {i}: {str(e)}")
        return screenshots

    async def cleanup_cache(self):
        """Clean up old cached screenshots"""
        try:
            # Wait for any pending tasks to complete
            if self.pending_tasks:
                await asyncio.gather(*self.pending_tasks)
            
            cache_files = list(self.cache_dir.glob("*.png"))
            if len(cache_files) > self.cleanup_threshold:
                # Sort by modification time
                cache_files.sort(key=lambda x: x.stat().st_mtime)
                
                # Remove oldest files
                files_to_remove = cache_files[:-self.cleanup_threshold]
                for file in files_to_remove:
                    file.unlink()
                
                logger.info(f"Cleaned up {len(files_to_remove)} cached screenshots")

        except Exception as e:
            logger.error(f"Cache cleanup failed: {str(e)}")

    async def get_pipeline_metrics(self) -> Dict:
        """Get screenshot pipeline metrics"""
        try:
            cache_files = list(self.cache_dir.glob("*.png"))
            total_size = sum(f.stat().st_size for f in cache_files)
            
            return {
                'cache_count': len(cache_files),
                'total_size_mb': total_size / (1024 * 1024),
                'avg_size_kb': (total_size / len(cache_files)) / 1024 if cache_files else 0,
                'oldest_file_age': datetime.now().timestamp() - min(f.stat().st_mtime for f in cache_files) if cache_files else 0,
                'newest_file_age': datetime.now().timestamp() - max(f.stat().st_mtime for f in cache_files) if cache_files else 0,
                'pending_tasks': len(self.pending_tasks),
                'compression_ratio': self._calculate_compression_ratio()
            }
        except Exception as e:
            logger.error(f"Failed to get metrics: {str(e)}")
            return {}

    def _calculate_compression_ratio(self) -> float:
        """Calculate average compression ratio"""
        try:
            cache_files = list(self.cache_dir.glob("*.png"))
            if not cache_files:
                return 0.0
            
            ratios = []
            for cache_file in cache_files:
                original_size = cache_file.stat().st_size
                with Image.open(cache_file) as img:
                    # Create temporary buffer for uncompressed size
                    temp_buffer = io.BytesIO()
                    img.save(temp_buffer, format='PNG', optimize=False)
                    uncompressed_size = temp_buffer.tell()
                    ratios.append(original_size / uncompressed_size)
            
            return sum(ratios) / len(ratios)
            
        except Exception as e:
            logger.error(f"Failed to calculate compression ratio: {str(e)}")
            return 0.0

    async def cleanup_all(self):
        """Clean up all resources"""
        try:
            # Cancel any pending tasks
            for task in self.pending_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            # Wait for cancellation to complete
            if self.pending_tasks:
                await asyncio.gather(*self.pending_tasks, return_exceptions=True)
            
            # Clear cache
            for file in self.cache_dir.glob("*.png"):
                file.unlink()
            
            # Shutdown thread pool
            self.thread_pool.shutdown(wait=True)
            
            logger.info("Screenshot pipeline cleanup completed")
            
        except Exception as e:
            logger.error(f"Pipeline cleanup failed: {str(e)}")


# Export ScreenshotPipeline class
__all__ = ['ScreenshotPipeline']
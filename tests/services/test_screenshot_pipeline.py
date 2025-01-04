import pytest
from pathlib import Path
from PIL import Image
import io
from src.services.screenshot_pipeline import ScreenshotPipeline
from src.services.screenshot_manager import ScreenshotManager
from src.utils.exceptions import ScreenshotError

@pytest.fixture
def screenshot_pipeline(screenshot_manager):
    return ScreenshotPipeline(screenshot_manager)

class TestScreenshotPipeline:
    async def test_capture_optimized(self, screenshot_pipeline, mock_page, tmp_path):
        # Create a test image
        test_img = Image.new('RGB', (2000, 2000), color='white')
        test_path = tmp_path / "test.png"
        test_img.save(test_path)

        # Test optimization
        optimized_path = await screenshot_pipeline.capture_optimized(
            name="test_capture"
        )
        
        assert optimized_path.exists()
        with Image.open(optimized_path) as img:
            assert max(img.size) <= screenshot_pipeline.max_dimension

    async def test_capture_parallel(self, screenshot_pipeline, mock_page):
        await mock_page.set_content("""
            <div id="test1">Test 1</div>
            <div id="test2">Test 2</div>
            <div id="test3">Test 3</div>
        """)
        
        results = await screenshot_pipeline.capture_parallel(
            ["#test1", "#test2", "#test3"],
            "parallel_test"
        )
        
        assert len(results) == 3
        assert all(isinstance(r, Path) for r in results)

    async def test_cleanup_cache(self, screenshot_pipeline, tmp_path):
        # Create test files
        for i in range(screenshot_pipeline.cleanup_threshold + 5):
            test_path = screenshot_pipeline.cache_dir / f"test_{i}.png"
            Image.new('RGB', (100, 100)).save(test_path)

        await screenshot_pipeline.cleanup_cache()
        
        remaining_files = list(screenshot_pipeline.cache_dir.glob("*.png"))
        assert len(remaining_files) <= screenshot_pipeline.cleanup_threshold

    def test_optimize_image(self, screenshot_pipeline, tmp_path):
        # Create large test image
        large_img = Image.new('RGB', (3000, 3000), color='white')
        input_path = tmp_path / "large.png"
        output_path = tmp_path / "optimized.png"
        large_img.save(input_path)

        result_path = screenshot_pipeline._optimize_image(input_path, output_path)
        
        with Image.open(result_path) as img:
            assert max(img.size) <= screenshot_pipeline.max_dimension
#test/services/test_screenshot_manager.py
class TestScreenshotManager:
    async def test_capture_and_optimize(self, screenshot_manager, mock_page):
        # Setup mock page content
        await mock_page.set_content("<html><body><div>Test</div></body></html>")
        
        screenshot = await screenshot_manager.capture(
            name="test",
            optimize=True
        )
        assert screenshot.exists()
        assert screenshot.suffix == ".png"

    async def test_parallel_capture(self, screenshot_manager, mock_page):
        await mock_page.set_content("""
            <html><body>
                <div id="div1">Test 1</div>
                <div id="div2">Test 2</div>
            </body></html>
        """)
        
        screenshots = await screenshot_manager.capture_multiple(
            ["#div1", "#div2"],
            "test_multi"
        )
        assert len(screenshots) == 2
        assert all(s.exists() for s in screenshots)
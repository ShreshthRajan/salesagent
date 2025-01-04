import pytest
from unittest.mock import patch, AsyncMock
from src.utils.exceptions import VisionAPIError

class TestVisionService:
    async def test_analyze_screenshot_with_context(self, vision_service, tmp_path):
        test_image = tmp_path / "test.png"
        test_image.write_bytes(b"test image data")
        
        mock_response = {
            "choices": [{
                "message": {
                    "content": '{"page_state": "search", "elements": [], "next_action": {"type": "click", "target": "button"}}'
                }
            }]
        }
        
        with patch("aiohttp.ClientSession.post", AsyncMock(return_value=AsyncMock(
            status=200,
            json=AsyncMock(return_value=mock_response)
        ))):
            result = await vision_service.analyze_with_context(
                test_image,
                {"state": "initial"}
            )
            assert result["page_state"] == "search"

    async def test_dynamic_prompt_generation(self, vision_service):
        prompt = vision_service._get_dynamic_template(
            'search',
            context='{"state": "initial"}',
            previous_state=None
        )
        assert "search interface" in prompt.lower()
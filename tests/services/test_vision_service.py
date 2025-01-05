# tests/services/test_vision_service.py
import pytest
from unittest.mock import patch, AsyncMock
from src.services.vision_service import VisionService
from src.utils.exceptions import VisionAPIError
from src.utils.config import Config, ApiConfigs, OpenAIConfig, APIConfig, BrowserConfig, ProxyConfig, LoggingConfig

@pytest.fixture
def mock_config():
    from src.utils.config import Config, ApiConfigs, APIConfig, OpenAIConfig
    return Config(
        api=ApiConfigs(
            apollo=APIConfig(base_url="", rate_limit=0),
            rocketreach=APIConfig(base_url="", rate_limit=0),
            openai=OpenAIConfig(
                api_key="test-key",
                base_url="https://api.openai.com/v1",
                rate_limit=50,
                model="gpt-4-vision-preview",
                temperature=0.1
            )
        )
    )

@pytest.fixture
def vision_service(mock_config):
    service = VisionService()
    service._config = mock_config  # Use private attribute to ensure config is set
    service.api_key = mock_config.api.openai.api_key
    return service

class TestVisionService:
    @pytest.mark.asyncio
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
            json=AsyncMock(return_value=mock_response),
            text=AsyncMock(return_value="")
        ))):
            result = await vision_service.analyze_with_context(
                test_image,
                {"state": "initial"}
            )
            assert result["page_state"] == "search"
    
    @pytest.mark.asyncio
    async def test_dynamic_prompt_generation(self, vision_service):
        prompt = vision_service._get_dynamic_template(
            'search',
            context='{"state": "initial"}',
            previous_state=None
        )
        assert "search interface" in prompt.lower()

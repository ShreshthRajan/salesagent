# tests/services/test_vision_service.py
import pytest
from unittest.mock import patch, AsyncMock
from src.services.vision_service import VisionService
from src.utils.exceptions import VisionAPIError
from src.utils.config import Config, ApiConfigs, OpenAIConfig, APIConfig, BrowserConfig, ProxyConfig, LoggingConfig

@pytest.fixture
def mock_config():
    from src.utils.config import Config, ApiConfigs, APIConfig, OpenAIConfig, BrowserConfig, ProxyConfig, LoggingConfig
    
    openai_config = OpenAIConfig(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        rate_limit=50,
        model="gpt-4-vision-preview",
        temperature=0.1
    )
    
    api_configs = ApiConfigs(
        apollo=APIConfig(base_url="", rate_limit=0),
        rocketreach=APIConfig(base_url="", rate_limit=0),
        openai=openai_config
    )
    
    return Config(
        api=api_configs,
        browser=BrowserConfig(),
        proxies=ProxyConfig(),
        logging=LoggingConfig()
    )

@pytest.fixture
def vision_service(mock_config):
    with patch('src.utils.config.ConfigManager') as MockConfigManager:
        instance = MockConfigManager.return_value
        instance.config = mock_config
        service = VisionService()
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

        # Create a proper mock response object
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json.return_value = mock_response
        mock_resp.text.return_value = ""
        
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.post.return_value = mock_resp
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await vision_service.analyze_with_context(
                test_image,
                {"state": "initial"}
            )
            assert result["page_state"] == "search"
    
    @pytest.mark.asyncio
    async def test_dynamic_prompt_generation(self, vision_service):
        # Ensure templates are loaded
        vision_service._load_prompt_templates()
        
        prompt = vision_service._get_dynamic_template(
            'search',
            context='{"state": "initial"}',
            previous_state=None
        )
        assert "search interface" in prompt.lower()

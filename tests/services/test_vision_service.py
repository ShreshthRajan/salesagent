# tests/services/test_vision_service.py
import pytest
from unittest.mock import patch, AsyncMock
from src.services.vision_service import VisionService
from src.utils.exceptions import VisionAPIError
from src.utils.config import Config, ApiConfigs, OpenAIConfig, APIConfig, BrowserConfig, ProxyConfig, LoggingConfig

@pytest.fixture
def mock_config():
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
        service.cache_hits = 0
        service.cache_misses = 0
        service.transition_attempts = 0
        service.successful_transitions = 0
        return service

async def mock_make_request(mock_response):
    """Helper to create a mock response for _make_request"""
    async def _mock(*args, **kwargs):
        return mock_response
    return _mock

class TestVisionService:
    @pytest.mark.asyncio
    async def test_analyze_screenshot_with_context(self, vision_service, tmp_path):
        test_image = tmp_path / "test.png"
        test_image.write_bytes(b"test image data")
        
        mock_response = {
            "choices": [{
                "message": {
                    "content": '{"page_state": "search", "confidence": 0.9, "elements": [], "next_action": {"type": "click", "target": "button", "confidence": 0.8}}'
                }
            }]
        }

        # Mock _make_request instead of session.post
        with patch.object(vision_service, '_make_request', new_callable=AsyncMock,
                         return_value=mock_response):
            with patch.object(vision_service, '_encode_image', 
                            new_callable=AsyncMock, return_value="mock_base64"):
                result = await vision_service.analyze_with_context(
                    test_image,
                    {"state": "initial"}
                )
                
                assert isinstance(result, dict)
                assert result["page_state"] == "search"
                assert "elements" in result
                assert "next_action" in result

    @pytest.mark.asyncio
    async def test_analyze_screenshot_retry_logic(self, vision_service, tmp_path):
        test_image = tmp_path / "test.png"
        test_image.write_bytes(b"test image data")

        mock_success_response = {
            "choices": [{
                "message": {
                    "content": '{"page_state": "search", "confidence": 0.9, "elements": [], "next_action": {"type": "click", "target": "button", "confidence": 0.8}}'
                }
            }]
        }

        # Set up _make_request to fail once then succeed
        mock_make_request = AsyncMock(side_effect=[
            VisionAPIError("Test error"),
            mock_success_response
        ])

        # Reduce retry delay for faster test
        vision_service.retry_config['base_delay'] = 0.1

        with patch.object(vision_service, '_make_request', mock_make_request):
            with patch.object(vision_service, '_encode_image',
                            new_callable=AsyncMock, return_value="mock_base64"):
                result = await vision_service.analyze_screenshot(test_image)
                assert result["page_state"] == "search"

    @pytest.mark.asyncio
    async def test_dynamic_prompt_generation(self, vision_service):
        vision_service._load_prompt_templates()
        prompt = vision_service._get_dynamic_template(
            'search',
            context='{"state": "initial"}',
            previous_state=None
        )
        assert "search interface" in prompt.lower()

    @pytest.mark.asyncio
    async def test_validate_state_transition(self, vision_service, tmp_path):
        before_image = tmp_path / "before.png"
        after_image = tmp_path / "after.png"
        before_image.write_bytes(b"test before data")
        after_image.write_bytes(b"test after data")

        mock_responses = [
            {
                "choices": [{
                    "message": {
                        "content": '{"page_state": "initial", "confidence": 0.9, "elements": [], "next_action": {"type": "click", "target": "button", "confidence": 0.8}}'
                    }
                }]
            },
            {
                "choices": [{
                    "message": {
                        "content": '{"page_state": "final", "confidence": 0.95, "elements": [], "next_action": {"type": "click", "target": "button", "confidence": 0.8}}'
                    }
                }]
            }
        ]

        # Mock _make_request to return different responses for before and after states
        mock_make_request = AsyncMock(side_effect=mock_responses)

        with patch.object(vision_service, '_make_request', mock_make_request):
            with patch.object(vision_service, '_encode_image',
                            new_callable=AsyncMock, return_value="mock_base64"):
                result = await vision_service.validate_state_transition(
                    before_image,
                    after_image,
                    "final"
                )
                assert result is True 

# done 
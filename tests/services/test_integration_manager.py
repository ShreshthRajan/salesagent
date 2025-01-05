# tests/services/test_integration_manager.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from src.services.integration_manager import IntegrationManager
from src.utils.exceptions import IntegrationError, VisionAPIError
from src.utils.config import Config, ApiConfigs, APIConfig, OpenAIConfig, BrowserConfig, ProxyConfig, LoggingConfig

@pytest.fixture
def mock_config():
    return Config(
        api=ApiConfigs(
            apollo=APIConfig(
                base_url="https://api.apollo.com",
                rate_limit=100,
                api_key="test_apollo_key"
            ),
            rocketreach=APIConfig(
                base_url="https://api.rocketreach.com",
                rate_limit=100,
                api_key="test_rocketreach_key"
            ),
            openai=OpenAIConfig(
                api_key="test_openai_key",
                base_url="https://api.openai.com/v1",
                rate_limit=50,
                model="gpt-4-test",
                temperature=0.2
            )
        ),
        browser=BrowserConfig(
            max_concurrent=5,
            timeout=30000,
            retry_attempts=3
        ),
        proxies=ProxyConfig(
            rotation_interval=300,
            max_failures=3
        ),
        logging=LoggingConfig(
            level="DEBUG",
            format="json"
        )
    )

@pytest.fixture
def integration_manager(mock_config):
    # Mock all dependencies
    page = Mock()  # Mock the Playwright Page
    vision_service = Mock()
    vision_service.analyze_screenshot = AsyncMock(return_value={"page_state": "search"})
    action_parser = Mock()
    action_parser.parse_action = AsyncMock(return_value=({"type": "click", "target": "button"}, []))
    state_machine = Mock()
    state_machine.transition = AsyncMock(return_value=None)
    validation_service = Mock()
    validation_service.validate_action = AsyncMock(return_value=Mock(is_valid=True))
    screenshot_pipeline = Mock()
    screenshot_pipeline.capture_optimized = AsyncMock(return_value="path/to/screenshot.png")
    element_handler = Mock()
    element_handler.click = AsyncMock(return_value=None)
    
    manager = IntegrationManager(
        page=page,
        vision_service=vision_service,
        action_parser=action_parser,
        state_machine=state_machine,
        validation_service=validation_service,
        screenshot_pipeline=screenshot_pipeline,
        element_handler=element_handler
    )
    return manager

class TestIntegrationManager:
    @pytest.mark.asyncio
    async def test_execute_vision_action(self, integration_manager):
        # Mock screenshot pipeline
        integration_manager.screenshot_pipeline.capture_optimized = AsyncMock(
            return_value="test_screenshot.png"
        )
        
        # Mock vision service
        integration_manager.vision_service.analyze_screenshot = AsyncMock(
            return_value={
                "page_state": "search",
                "next_action": {
                    "type": "click",
                    "target": {"selector": "#search-button"},
                    "confidence": 0.95
                }
            }
        )
        
        # Mock action parser
        integration_manager.action_parser.parse_action = AsyncMock(
            return_value=(
                {
                    "type": "click",
                    "target": {"selector": "#search-button"}
                },
                []
            )
        )
        
        # Mock validation service
        integration_manager.validation_service.validate_action = AsyncMock(
            return_value=Mock(is_valid=True, confidence=0.95, errors=[])
        )
        
        # Mock element handler
        integration_manager.element_handler.click = AsyncMock(return_value=True)
        
        # Execute and verify
        result = await integration_manager.execute_vision_action()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_error_handling(self, integration_manager):
        with patch("src.services.vision_service.VisionService.analyze_screenshot",
                  AsyncMock(side_effect=VisionAPIError("API Error"))):
            result = await integration_manager.execute_vision_action()
            assert result is False

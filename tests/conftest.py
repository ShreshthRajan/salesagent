"""
Fixtures for integration testing
"""
import sys
import pytest
import asyncio
from pathlib import Path
import pytest_asyncio
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from src.utils.config import Config, APIConfig, ApiConfigs, BrowserConfig, LoggingConfig, OpenAIConfig, ProxyConfig

load_dotenv()

@pytest_asyncio.fixture(scope="class")
async def event_loop():
    """Create and yield an event loop for each test class"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="class")
async def mock_config():
    """Create mock configuration for testing"""
    return Config(
        api=ApiConfigs(
            apollo=APIConfig(
                base_url="https://app.apollo.io",
                rate_limit=100,
                api_key="test-key"  # Added required field
            ),
            rocketreach=APIConfig(
                base_url="https://rocketreach.co",
                rate_limit=50,
                api_key="test-key"  # Added required field
            ),
            openai=OpenAIConfig(
                api_key="test-key",  # Added required field
                base_url="https://api.openai.com/v1",
                rate_limit=50,
                model="gpt-4-vision-preview",
                temperature=0.1
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
            level="INFO",
            format="json"
        )
    )

@pytest_asyncio.fixture(scope="class")
async def browser_context(event_loop):
    """Create browser context for testing"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720}
        )
        yield context
        await context.close()
        await browser.close()

@pytest_asyncio.fixture(scope="class")
async def services(browser_context, mock_config):
    """Initialize all required services"""
    from src.services.vision_service import VisionService
    from src.services.action_parser import ActionParser
    from src.services.navigation_state import NavigationStateMachine
    from src.services.validation_service import ValidationService
    from src.services.screenshot_pipeline import ScreenshotPipeline
    from src.services.result_collector import ResultCollector
    
    # Initialize services with mock config
    vision_service = VisionService()
    action_parser = ActionParser()
    state_machine = NavigationStateMachine()
    validation_service = ValidationService()
    screenshot_pipeline = ScreenshotPipeline(browser_context.pages[0])
    result_collector = ResultCollector()
    
    yield {
        'vision_service': vision_service,
        'action_parser': action_parser,
        'state_machine': state_machine,
        'validation_service': validation_service,
        'screenshot_pipeline': screenshot_pipeline,
        'result_collector': result_collector,
        'browser_context': browser_context,
        'config': mock_config
    }
    
    # Cleanup
    await state_machine.cleanup()
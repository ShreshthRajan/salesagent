# tests/conftest.py
import sys
from mock import patch 
import pytest
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from unittest.mock import MagicMock
from src.services.vision_service import VisionService
from src.services.action_parser import ActionParser
from src.services.navigation_state import NavigationStateMachine
from src.services.validation_service import ValidationService
from src.services.screenshot_manager import ScreenshotManager
from src.services.integration_manager import IntegrationManager
from dotenv import load_dotenv
import pytest_asyncio
from src.utils.config import APIConfig, ApiConfigs, BrowserConfig, LoggingConfig, OpenAIConfig, ProxyConfig 
from src.utils.config import Config

load_dotenv()

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
def event_loop_policy():
    return asyncio.WindowsSelectorEventLoopPolicy() if sys.platform == 'win32' else asyncio.DefaultEventLoopPolicy()

@pytest_asyncio.fixture(scope="function")
async def event_loop(event_loop_policy):
    policy = event_loop_policy
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)

@pytest_asyncio.fixture(scope="function")
async def cleanup_tasks():
    yield
    # Get all tasks from the current event loop
    loop = asyncio.get_event_loop()
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
    
    # Cancel all tasks
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

@pytest.fixture
async def browser_context():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()
        yield context
        await context.close()
        await browser.close()

@pytest.fixture
async def mock_page(browser_context):
    page = await browser_context.new_page()
    yield page
    await page.close()

@pytest.fixture
def screenshot_manager(mock_page):
    return ScreenshotManager(mock_page)

@pytest.fixture
def vision_service():
    service = VisionService()
    service.api_key = "test_key"
    return service

@pytest.fixture
def action_parser():
    return ActionParser()

@pytest.fixture
async def navigation_state(cleanup_tasks):
    state = NavigationStateMachine()
    yield state
    await state.cleanup()

@pytest.fixture
def validation_service():
    return ValidationService()

@pytest.fixture
def integration_manager(mock_page, vision_service, action_parser, navigation_state, 
                       validation_service, screenshot_manager):
    return IntegrationManager(
        mock_page,
        vision_service,
        action_parser,
        navigation_state,
        validation_service,
        screenshot_manager
    )

@pytest.fixture
def mock_config():
    from src.utils.config import Config, ApiConfigs, OpenAIConfig, APIConfig, BrowserConfig, ProxyConfig, LoggingConfig
    
    return Config(
        api=ApiConfigs(
            apollo=APIConfig(base_url="", rate_limit=0),
            rocketreach=APIConfig(base_url="", rate_limit=0),
            openai=OpenAIConfig()
        ),
        browser=BrowserConfig(max_concurrent=5, timeout=30000, retry_attempts=3),
        proxies=ProxyConfig(rotation_interval=300, max_failures=3),
        logging=LoggingConfig(level="INFO", format="json")
    )

@pytest.fixture
def vision_service(mock_config):
    service = VisionService()
    service.config = mock_config
    return service

@pytest.fixture(autouse=True)
def mock_config_manager():
    with patch('src.utils.config.ConfigManager') as mock:
        instance = mock.return_value
        instance.config = Config(
            api=ApiConfigs(
                apollo=APIConfig(base_url="", rate_limit=0),
                rocketreach=APIConfig(base_url="", rate_limit=0),
                openai=OpenAIConfig()
            ),
            browser=BrowserConfig(),
            proxies=ProxyConfig(),
            logging=LoggingConfig()
        )
        yield mock
# src/tests/conftest.py
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

# Change scope to "class" to match test class fixtures
@pytest.fixture(scope="class")
def event_loop_policy():
    return asyncio.WindowsSelectorEventLoopPolicy() if sys.platform == 'win32' else asyncio.DefaultEventLoopPolicy()

@pytest_asyncio.fixture(scope="class")
async def event_loop(event_loop_policy):
    policy = event_loop_policy
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)

@pytest_asyncio.fixture(scope="class")
async def event_loop():
    """Create and yield an event loop for each test class"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

    
@pytest_asyncio.fixture(scope="class")
async def cleanup_tasks():
    yield
    loop = asyncio.get_event_loop()
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

@pytest_asyncio.fixture(scope="class")
async def browser_context(event_loop):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Set to true for production
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720}
        )
        yield context
        await context.close()
        await browser.close()

@pytest_asyncio.fixture(scope="class")
async def mock_config():
    return Config(
        api=ApiConfigs(
            apollo=APIConfig(
                base_url="https://app.apollo.io",
                rate_limit=100
            ),
            rocketreach=APIConfig(
                base_url="https://rocketreach.co",
                rate_limit=50
            ),
            openai=OpenAIConfig(
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
async def services(browser_context, mock_config):
    vision_service = VisionService()
    action_parser = ActionParser()
    state_machine = NavigationStateMachine()
    validation_service = ValidationService()
    screenshot_manager = ScreenshotManager(browser_context.pages[0])
    
    yield {
        'vision_service': vision_service,
        'action_parser': action_parser,
        'state_machine': state_machine,
        'validation_service': validation_service,
        'screenshot_manager': screenshot_manager,
        'browser_context': browser_context
    }

    # Cleanup
    await state_machine.cleanup()
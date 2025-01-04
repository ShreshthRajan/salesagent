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

load_dotenv()

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

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
def navigation_state():
    return NavigationStateMachine()

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
"""
tests/agents/test_apollo_autonomous_agent.py
Tests for Apollo autonomous agent
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime
from playwright.async_api import Page, TimeoutError

from src.agents.apollo_autonomous_agent import ApolloAutonomousAgent
from src.services.vision_service import VisionService
from src.services.action_parser import ActionParser
from src.services.navigation_state import NavigationStateMachine
from src.services.validation_service import ValidationService
from src.services.screenshot_pipeline import ScreenshotPipeline
from src.utils.exceptions import AutomationError

@pytest.fixture
async def mock_page():
    """Mock Playwright page"""
    page = AsyncMock(spec=Page)
    # Add all required async methods
    page.wait_for_selector = AsyncMock()
    page.click = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.get_by_role = AsyncMock(return_value=AsyncMock())
    page.query_selector_all = AsyncMock(return_value=[])
    return page

@pytest.fixture
def mock_vision_service():
    """Mock vision service"""
    service = Mock(spec=VisionService)
    service.analyze_screenshot = AsyncMock(return_value={
        "page_state": "login",
        "elements": [{"type": "button", "text": "Log In"}]
    })
    return service

@pytest.fixture
def mock_action_parser():
    """Mock action parser"""
    return Mock(spec=ActionParser)

@pytest.fixture
def mock_state_machine():
    """Mock state machine"""
    return Mock(spec=NavigationStateMachine)

@pytest.fixture
def mock_validation_service():
    """Mock validation service"""
    return Mock(spec=ValidationService)

@pytest.fixture
def mock_screenshot_pipeline():
    """Mock screenshot pipeline"""
    pipeline = Mock(spec=ScreenshotPipeline)
    pipeline.capture_optimized = AsyncMock()
    return pipeline

@pytest.fixture
async def agent(
    mock_page,
    mock_vision_service,
    mock_action_parser,
    mock_state_machine,
    mock_validation_service,
    mock_screenshot_pipeline
):
    """Create test agent with mock dependencies"""
    return ApolloAutonomousAgent(
        page=mock_page,
        vision_service=mock_vision_service,
        action_parser=mock_action_parser,
        state_machine=mock_state_machine,
        validation_service=mock_validation_service,
        screenshot_pipeline=mock_screenshot_pipeline
    )

@pytest.mark.asyncio
async def test_login_success(agent, mock_page):
    """Test successful login flow"""
    # Setup proper mock responses
    mock_page.wait_for_selector = AsyncMock(return_value=AsyncMock())
    mock_page.get_by_role = AsyncMock(return_value=AsyncMock())
    mock_page.click = AsyncMock()
    mock_page.wait_for_load_state = AsyncMock()
    
    # Mock vision service response
    agent.vision_service.analyze_screenshot.return_value = {
        "page_state": "login",
        "elements": [{"type": "button", "text": "Log In"}]
    }
    
    # Execute login
    result = await agent.login("test@example.com", "password123")
    
    assert result is True
    # Verify proper method calls
    mock_page.goto.assert_awaited_once_with("https://app.apollo.io/")

@pytest.mark.asyncio
async def test_login_failure(agent, mock_page):
    """Test login failure handling"""
    # Setup mock to simulate timeout
    mock_page.wait_for_selector.side_effect = PlaywrightTimeout("timeout")
    mock_page.goto = AsyncMock()  # Ensure this doesn't fail
    
    # Execute and verify
    with pytest.raises(AutomationError) as exc_info:
        await agent.login("test@example.com", "password123")
    assert "Failed to login" in str(exc_info.value)

@pytest.mark.asyncio
async def test_search_company(agent, mock_page):
    """Test company search flow"""
    # Setup mock responses
    mock_page.query_selector_all.return_value = [
        AsyncMock(
            query_selector=AsyncMock(
                return_value=AsyncMock(
                    inner_text=AsyncMock(return_value="Chief Executive Officer")
                )
            )
        )
    ]
    
    # Mock successful email reveal
    async def mock_extract_info(row):
        return {
            "name": "John Doe",
            "title": "Chief Executive Officer",
            "email": "john@example.com"
        }
    agent._extract_contact_info = mock_extract_info
    
    # Execute search
    results = await agent.search_company("Test Company")
    
    # Verify
    assert len(results) == 1
    assert results[0]["name"] == "John Doe"
    assert results[0]["title"] == "Chief Executive Officer"
    assert mock_page.click.await_count >= 3  # Navigation clicks

@pytest.mark.asyncio
async def test_rate_limiting(agent):
    """Test rate limiting behavior"""
    # Test search rate limiting
    start_time = datetime.now()
    await agent._wait_for_rate_limit("search")
    await agent._wait_for_rate_limit("search")
    duration = (datetime.now() - start_time).total_seconds()
    
    assert duration >= agent.search_delay.total_seconds()

@pytest.mark.asyncio
async def test_extract_matching_contacts(agent, mock_page):
    """Test contact extraction with title matching"""
    # Setup mock data
    mock_rows = [
        AsyncMock(  # Matching title
            query_selector=AsyncMock(side_effect=lambda selector: {
                ".job-title": AsyncMock(inner_text=AsyncMock(return_value="CEO")),
                ".contact-name": AsyncMock(inner_text=AsyncMock(return_value="John Doe")),
                'button:has-text("Access email")': AsyncMock(),
                ".revealed-email": AsyncMock(inner_text=AsyncMock(return_value="john@example.com"))
            }.get(selector))
        ),
        AsyncMock(  # Non-matching title
            query_selector=AsyncMock(side_effect=lambda selector: {
                ".job-title": AsyncMock(inner_text=AsyncMock(return_value="Engineer")),
                ".contact-name": AsyncMock(inner_text=AsyncMock(return_value="Jane Doe"))
            }.get(selector))
        )
    ]
    
    mock_page.query_selector_all.return_value = mock_rows
    mock_page.query_selector.return_value = AsyncMock(is_disabled=AsyncMock(return_value=True))
    
    # Execute
    contacts = await agent._extract_matching_contacts()
    
    # Verify
    assert len(contacts) == 1
    assert contacts[0]["name"] == "John Doe"
    assert contacts[0]["title"] == "CEO"
    assert contacts[0]["email"] == "john@example.com"

@pytest.mark.asyncio
async def test_error_handling(agent, mock_page):
    """Test error handling during extraction"""
    # Setup mock to raise error
    mock_page.query_selector_all.side_effect = Exception("Network error")
    mock_page.goto = AsyncMock()
    
    # Execute
    results = await agent._extract_matching_contacts()
    assert len(results) == 0
    # Update error count assertion
    assert agent.error_count == 1

@pytest.mark.asyncio
async def test_human_like_behavior(agent):
    """Test human-like typing and delay behavior"""
    # Test typing with delays
    start_time = datetime.now()
    await agent._type_with_random_delays(
        "input",
        "test",
        delay_range=(0.1, 0.2)
    )
    duration = (datetime.now() - start_time).total_seconds()
    
    # Should take at least 0.3 seconds (0.1 * 3 characters minimum)
    assert duration >= 0.3
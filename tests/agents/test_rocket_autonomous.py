"""
Tests for the RocketReach autonomous agent
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
import logging

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from src.services.vision_service import VisionService
from src.services.action_parser import ActionParser
from src.services.navigation_state import NavigationStateMachine
from src.services.validation_service import ValidationService, ValidationResult
from src.services.screenshot_pipeline import ScreenshotPipeline
from src.services.result_collector import ResultCollector, SearchResult
from src.agents.rocket_autonomous_agent import RocketReachAgent
from src.utils.exceptions import AutomationError, ValidationError

# Disable asyncio debug mode to prevent task tracking issues
logging.getLogger("asyncio").setLevel(logging.WARNING)

# Test constants
MOCK_VISION_RESULT = {
    'page_state': 'search',
    'confidence': 0.9,
    'elements': [
        {
            'type': 'button',
            'text': 'Search',
            'location': {'x': 100, 'y': 100},
            'confidence': 0.95
        }
    ],
    'next_action': {
        'type': 'click',
        'target': {'selector': '#search-button'},
        'confidence': 0.9
    }
}

MOCK_CONTACT = {
    'name': 'John Doe',
    'title': 'Chief Executive Officer',
    'company': 'Test Company',
    'email': 'john@test.com',
    'confidence': 0.9
}

# Test fixtures
@pytest.fixture(scope='function')
async def mock_page():
    page = AsyncMock(spec=Page)
    # Setup default successful responses
    page.wait_for_selector = AsyncMock(return_value=AsyncMock())
    page.query_selector = AsyncMock(return_value=AsyncMock())
    page.evaluate = AsyncMock()
    page.goto = AsyncMock()
    page.locator = AsyncMock()
    page.mouse = AsyncMock()
    return page

@pytest.fixture(scope='function')
async def mock_vision_service():
    service = AsyncMock(spec=VisionService)
    service.analyze_screenshot.return_value = MOCK_VISION_RESULT
    service.analyze_with_context.return_value = MOCK_VISION_RESULT
    return service

@pytest.fixture(scope='function')
async def mock_action_parser():
    parser = AsyncMock(spec=ActionParser)
    parser.parse_action.return_value = (MOCK_VISION_RESULT['next_action'], [])
    return parser

@pytest.fixture(scope='function')
async def mock_state_machine():
    machine = AsyncMock(spec=NavigationStateMachine)
    return machine

@pytest.fixture(scope='function')
async def mock_validation_service():
    service = AsyncMock(spec=ValidationService)
    service.validate_action.return_value = ValidationResult(
        is_valid=True,
        confidence=0.9,
        errors=[]
    )
    service.validate_email.return_value = ValidationResult(
        is_valid=True,
        confidence=0.9,
        errors=[]
    )
    return service

@pytest.fixture(scope='function')
async def mock_screenshot_pipeline():
    pipeline = AsyncMock(spec=ScreenshotPipeline)
    pipeline.capture_optimized.return_value = "screenshot.png"
    return pipeline

@pytest.fixture(scope='function')
async def mock_result_collector():
    collector = AsyncMock(spec=ResultCollector)
    return collector

@pytest.fixture(scope='function')
async def agent(
    mock_page,
    mock_vision_service,
    mock_action_parser,
    mock_state_machine,
    mock_validation_service,
    mock_screenshot_pipeline,
    mock_result_collector
):
    agent = RocketReachAgent(
        mock_page,
        mock_vision_service,
        mock_action_parser,
        mock_state_machine,
        mock_validation_service,
        mock_screenshot_pipeline,
        mock_result_collector
    )
    # Setup default successful mocks
    agent._extract_contact_info = AsyncMock(return_value=MOCK_CONTACT)
    agent._execute_action = AsyncMock(return_value=True)
    return agent

@pytest.mark.asyncio
async def test_login_success(agent):
    """Test successful login flow"""
    # Setup
    email = "test@example.com"
    password = "password123"
    
    # Configure mocks for successful login
    agent.page.wait_for_selector = AsyncMock(return_value=AsyncMock())
    agent._type_with_validation = AsyncMock(return_value=ValidationResult(
        is_valid=True,
        confidence=1.0,
        errors=[]
    ))
    
    # Execute
    result = await agent.login(email, password)
    
    # Assert
    assert result is True
    agent.state_machine.transition.assert_called_once_with('init_login')
    agent.page.goto.assert_called_once_with("https://rocketreach.co/")

@pytest.mark.asyncio
async def test_login_failure(agent):
    """Test login failure handling"""
    # Setup
    email = "test@example.com"
    password = "password123"
    
    # Force error on selector wait
    agent.page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeoutError("Timeout"))
    agent.max_retries = 1  # Ensure quick failure
    
    # Execute & Assert
    with pytest.raises(AutomationError):
        await agent.login(email, password)

@pytest.mark.asyncio
async def test_search_company_success(agent):
    """Test successful company search"""
    # Setup
    domain = "test.com"
    
    # Mock successful company search
    agent._search_domain = AsyncMock(return_value=True)
    agent._extract_all_contacts = AsyncMock(return_value=[MOCK_CONTACT])
    
    # Execute
    results = await agent.search_company(domain)
    
    # Assert
    assert len(results) == 1
    assert results[0]['name'] == MOCK_CONTACT['name']
    agent.state_machine.transition.assert_called_with('init_search')

@pytest.mark.asyncio
async def test_extract_contacts_limit(agent):
    """Test contact extraction respects limits"""
    # Setup
    mock_contacts = [MOCK_CONTACT.copy() for _ in range(10)]
    agent._extract_page_contacts = AsyncMock(return_value=mock_contacts)
    
    # Execute
    results = await agent._extract_all_contacts()
    
    # Assert
    assert len(results) <= agent.max_results

@pytest.mark.asyncio
async def test_pagination(agent):
    """Test pagination functionality"""
    # Setup
    current_page = 1
    agent.page.query_selector = AsyncMock(return_value=AsyncMock())
    
    # Execute
    result = await agent._go_to_next_page(current_page)
    
    # Assert
    assert result is True
    assert agent.page.wait_for_load_state.called

@pytest.mark.asyncio
async def test_error_handling(agent):
    """Test error handling"""
    # Setup
    error = Exception("Test error")
    
    # Execute
    await agent._handle_error(error)
    
    # Assert
    assert agent.current_state['error_count'] == 1
    assert agent.current_state['last_action'] == 'error'

@pytest.mark.asyncio
async def test_rate_limit_handling(agent):
    """Test rate limit error handling"""
    # Setup
    error = Exception("rate limit exceeded")
    
    # Execute
    await agent._handle_error(error)
    
    # Assert
    assert agent.current_state['rate_limit_hits'] == 1

@pytest.mark.asyncio
async def test_cleanup(agent):
    """Test cleanup functionality"""
    # Execute
    await agent.cleanup()
    
    # Assert
    assert agent.current_state['error_count'] == 0
    assert agent.current_state['page_number'] == 1
    assert agent.state_machine.cleanup.called

@pytest.mark.asyncio
async def test_metrics(agent):
    """Test metrics collection"""
    # Setup
    agent.current_state['results_found'] = 5
    agent.current_state['error_count'] = 1
    
    # Execute
    metrics = agent.get_metrics()
    
    # Assert
    assert metrics['total_results'] == 5
    assert metrics['error_rate'] == 0.2
    assert 'pages_processed' in metrics

# Cleanup fixture to handle any remaining tasks
@pytest.fixture(autouse=True)
async def cleanup_async():
    yield
    # Get all tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    # Cancel them
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

        
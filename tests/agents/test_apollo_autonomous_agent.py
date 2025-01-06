"""
tests/agents/test_apollo_autonomous_agent.py
Tests for Apollo autonomous agent
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

from src.agents.apollo_autonomous_agent import ApolloAutonomousAgent
from src.services.vision_service import VisionService
from src.services.action_parser import ActionParser
from src.services.navigation_state import NavigationStateMachine, NavigationState
from src.services.validation_service import ValidationService, ValidationResult
from src.services.screenshot_pipeline import ScreenshotPipeline
from src.services.result_collector import ResultCollector, SearchResult
from src.utils.exceptions import AutomationError, ValidationError

@pytest.fixture
def mock_page():
    """Mock Playwright page with enhanced functionality"""
    page = AsyncMock(spec=Page)
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.wait_for_selector = AsyncMock(return_value=AsyncMock(
        type=AsyncMock(),
        input_value=AsyncMock(return_value="test@example.com"),
        inner_text=AsyncMock(return_value="test@example.com"),
        is_disabled=AsyncMock(return_value=False),
        click=AsyncMock(),
        press=AsyncMock(),
        get_attribute=AsyncMock(return_value=None)
    ))
    page.wait_for_load_state = AsyncMock()
    page.mouse = AsyncMock()
    page.mouse.click = AsyncMock()
    page.url = "https://app.apollo.io/dashboard"
    page.query_selector = AsyncMock(return_value=AsyncMock(
        is_visible=AsyncMock(return_value=True),
        input_value=AsyncMock(return_value="test@example.com"),
        inner_text=AsyncMock(return_value="test@example.com"),
        click=AsyncMock(),
        press=AsyncMock()
    ))
    page.query_selector_all = AsyncMock(return_value=[
        AsyncMock(
            query_selector=AsyncMock(return_value=AsyncMock(
                inner_text=AsyncMock(return_value="CEO"),
                click=AsyncMock()
            ))
        )
    ])
    return page

@pytest.fixture
def mock_vision_service():
    """Mock vision service with realistic responses"""
    service = Mock(spec=VisionService)
    service.analyze_screenshot = AsyncMock(return_value={
        'page_state': 'login',
        'confidence': 0.95,
        'next_action': {
            'type': 'click',
            'target': {'selector': 'button[type="submit"]'},
            'confidence': 0.9
        }
    })
    
    service.analyze_with_context = AsyncMock(return_value={
        'page_state': 'search',
        'confidence': 0.9,
        'next_action': {
            'type': 'type',
            'target': {'selector': 'input[type="text"]'},
            'value': 'Test Company',
            'confidence': 0.95
        },
        'contacts': [
            {
                'name': 'John Doe',
                'title': 'CEO',
                'email_button': '.reveal-email'
            }
        ]
    })
    
    service.get_state_analysis_metrics = Mock(return_value={
        'cache_hit_rate': 0.8,
        'avg_confidence': 0.9
    })
    
    return service

@pytest.fixture
def mock_action_parser():
    """Mock action parser"""
    parser = Mock(spec=ActionParser)
    parser.parse_action = AsyncMock(return_value=(
        {
            'type': 'click',
            'target': {'selector': 'button[type="submit"]'}
        },
        []  # fallback actions
    ))
    return parser

@pytest.fixture
def mock_state_machine():
    """Mock state machine"""
    machine = Mock(spec=NavigationStateMachine)
    machine.initialize_search = AsyncMock(return_value=Mock())
    machine.transition = AsyncMock()
    machine.get_metrics = Mock(return_value={'state_transitions': 5})
    machine.cleanup = AsyncMock()
    return machine

@pytest.fixture
def mock_validation_service():
    """Mock validation service with successful validations"""
    service = Mock(spec=ValidationService)
    service.validate_action = AsyncMock(return_value=ValidationResult(
        is_valid=True,
        confidence=0.9,
        errors=[]
    ))
    service.validate_email = AsyncMock(return_value=ValidationResult(
        is_valid=True,
        confidence=0.95,
        errors=[]
    ))
    service.validate_result = AsyncMock(return_value={'confidence': 0.9})
    return service

@pytest.fixture
def mock_screenshot_pipeline():
    """Mock screenshot pipeline"""
    pipeline = Mock(spec=ScreenshotPipeline)
    pipeline.capture_optimized = AsyncMock(return_value=Path("mock_screenshot.png"))
    return pipeline

@pytest.fixture
def mock_result_collector():
    """Mock result collector with results"""
    collector = Mock(spec=ResultCollector)
    collector.add_result = AsyncMock(return_value=True)
    collector.cleanup_cache = AsyncMock()
    collector.results = []  # Add this line to fix the metrics test
    return collector

@pytest.fixture
def agent(
    mock_page,
    mock_vision_service,
    mock_action_parser,
    mock_state_machine,
    mock_validation_service,
    mock_screenshot_pipeline,
    mock_result_collector
):
    """Create test agent with all mock dependencies"""
    return ApolloAutonomousAgent(
        page=mock_page,
        vision_service=mock_vision_service,
        action_parser=mock_action_parser,
        state_machine=mock_state_machine,
        validation_service=mock_validation_service,
        screenshot_pipeline=mock_screenshot_pipeline,
        result_collector=mock_result_collector
    )

@pytest.mark.asyncio
async def test_login_success(agent, mock_page, mock_vision_service):
    """Test successful login flow"""
    # Mock successful validations
    agent.validation_service.validate_action = AsyncMock(return_value=ValidationResult(
        is_valid=True,
        confidence=0.9,
        errors=[]
    ))
    
    # Mock successful element interactions
    mock_page.query_selector.return_value = AsyncMock(
        is_visible=AsyncMock(return_value=True),
        input_value=AsyncMock(return_value="test@example.com"),
        inner_text=AsyncMock(return_value="test@example.com"),
        click=AsyncMock()
    )
    
    result = await agent.login("test@example.com", "password123")
    assert result is True

@pytest.mark.asyncio
async def test_search_company(agent, mock_vision_service, mock_page):
    """Test company search flow"""
    # Set up mock responses for the search flow
    mock_vision_service.analyze_with_context.side_effect = [
        {  # First call - search navigation
            'page_state': 'search',
            'confidence': 0.95,
            'next_action': {
                'type': 'click',
                'target': {'selector': '.search-button'}
            }
        },
        {  # Second call - company search
            'page_state': 'results',
            'confidence': 0.95,
            'contacts': [
                {
                    'name': 'John Doe',
                    'title': 'CEO',
                    'email_button': '.reveal-email'
                }
            ]
        }
    ]
    
    # Mock the _extract_matching_contacts method
    async def mock_extract_contacts():
        return [{'name': 'John Doe', 'title': 'CEO', 'email': 'john@example.com'}]
    agent._extract_matching_contacts = mock_extract_contacts
    
    results = await agent.search_company("Test Company")
    assert len(results) == 1
    assert results[0]['name'] == 'John Doe'
    assert results[0]['title'] == 'CEO'

@pytest.mark.asyncio
async def test_contact_extraction(agent, mock_page):
    """Test contact extraction from results"""
    # Create mock row data
    mock_name = AsyncMock()
    mock_name.inner_text.return_value = "John Doe"
    
    mock_title = AsyncMock()
    mock_title.inner_text.return_value = "CEO"
    
    mock_email = AsyncMock()
    mock_email.inner_text.return_value = "john.doe@example.com"
    
    mock_button = AsyncMock()
    
    # Create first row with target title
    row1 = AsyncMock()
    async def mock_row1_selector(selector):
        if selector == "td:nth-child(1)":
            return mock_name
        elif selector == "td:nth-child(2)":
            return mock_title
        elif selector == "button:has-text('Access email')":
            return mock_button
        elif selector == ".revealed-email":
            return mock_email
        return None
    row1.query_selector.side_effect = mock_row1_selector
    
    # Create second row with non-target title
    row2 = AsyncMock()
    mock_other_title = AsyncMock()
    mock_other_title.inner_text.return_value = "Engineer"
    async def mock_row2_selector(selector):
        if selector == "td:nth-child(2)":
            return mock_other_title
        return None
    row2.query_selector.side_effect = mock_row2_selector
    
    # Setup mock page
    mock_page.wait_for_load_state = AsyncMock()
    mock_page.query_selector_all.return_value = [row1, row2]
    
    # Mock pagination to stop after first page
    mock_page.query_selector.return_value = None
    
    # Execute test
    results = await agent._extract_matching_contacts()
    
    # Verify results
    assert len(results) == 1
    assert results[0]["name"] == "John Doe"
    assert results[0]["title"] == "CEO"
    assert results[0]["email"] == "john.doe@example.com"

@pytest.mark.asyncio
async def test_error_handling(agent):
    """Test error handling and retries"""
    # Set lower threshold for testing
    agent.max_errors = 2
    
    # Mock navigation to always fail
    async def mock_failing_navigation():
        agent.current_state['error_count'] += 1
        raise AutomationError("Operation failed")
    
    # Replace navigation method with our failing mock
    agent._navigate_to_search = mock_failing_navigation
    
    # Execute test expecting failure
    with pytest.raises(AutomationError) as exc_info:
        try:
            await agent.search_company("Test Company")
        except AutomationError as e:
            # Verify error count before re-raising
            assert agent.current_state['error_count'] >= agent.max_errors
            raise
    
    # Verify error message
    assert "Too many errors" in str(exc_info.value)

def test_metrics(agent):
    """Test metrics collection"""
    metrics = agent.get_metrics()
    
    assert isinstance(metrics, dict)
    assert 'total_searches' in metrics
    assert 'error_count' in metrics
    assert 'navigation_metrics' in metrics
    assert 'vision_metrics' in metrics
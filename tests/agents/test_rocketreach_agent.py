# salesagent/salesagent/tests/agents/test_rocketreach_agent.py
import pytest
from unittest.mock import patch
from agents.old_rocketreach_agent import RocketReachAgent
from tests.helpers import MockHTTPResponse, MockAioHTTPClient

@pytest.fixture
def rocketreach_agent():
    """Create RocketReachAgent instance with mocked config"""
    with patch('src.utils.config.ConfigManager') as mock_config:
        mock_config().config.api.rocketreach.base_url = "http://test"
        mock_config().config.api.rocketreach.api_key = "test_key"
        return RocketReachAgent()

@pytest.mark.asyncio
async def test_find_company_person(rocketreach_agent):
    """Test finding a person at a company"""
    mock_responses = {
        "person/search": MockHTTPResponse({
            "profiles": [{
                "id": "123",
                "name": "Jane Doe",
                "current_title": "CFO",
                "current_employer": "Test Company"
            }]
        })
    }

    mock_client = MockAioHTTPClient(mock_responses)

    with patch('aiohttp.ClientSession', return_value=mock_client):
        result = await rocketreach_agent.find_company_person("Test Company")
        assert result is not None
        assert result["name"] == "Jane Doe"
        assert result["title"] == "CFO"
        assert result["company"] == "Test Company"

@pytest.mark.asyncio
async def test_get_email(rocketreach_agent):
    """Test getting email for a person"""
    mock_responses = {
        "person/lookup": MockHTTPResponse({
            "emails": ["jane@example.com"]
        })
    }

    mock_client = MockAioHTTPClient(mock_responses)

    with patch('aiohttp.ClientSession', return_value=mock_client):
        email = await rocketreach_agent.get_email({"id": "123"})
        assert email == "jane@example.com"

@pytest.mark.asyncio
async def test_find_company_person_not_found(rocketreach_agent):
    """Test handling when no person is found"""
    mock_responses = {
        "person/search": MockHTTPResponse({
            "profiles": []
        })
    }

    mock_client = MockAioHTTPClient(mock_responses)

    with patch('aiohttp.ClientSession', return_value=mock_client):
        result = await rocketreach_agent.find_company_person("Test Company")
        assert result is None

@pytest.mark.asyncio
async def test_get_email_not_found(rocketreach_agent):
    """Test handling when email is not found"""
    mock_responses = {
        "person/lookup": MockHTTPResponse({
            "emails": []
        })
    }

    mock_client = MockAioHTTPClient(mock_responses)

    with patch('aiohttp.ClientSession', return_value=mock_client):
        email = await rocketreach_agent.get_email({"id": "123"})
        assert email is None
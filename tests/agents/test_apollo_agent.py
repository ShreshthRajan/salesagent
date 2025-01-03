# salesagent/salesagent/tests/agents/test_apollo_agent.py
import pytest
from unittest.mock import patch
from src.agents.apollo_agent import ApolloAgent
from tests.helpers import MockHTTPResponse, MockAioHTTPClient

@pytest.fixture
def apollo_agent():
    """Create ApolloAgent instance with mocked config"""
    with patch('src.utils.config.ConfigManager') as mock_config:
        mock_config().config.api.apollo.base_url = "http://test"
        mock_config().config.api.apollo.api_key = "test_key"
        return ApolloAgent()

@pytest.mark.asyncio
async def test_find_company_person(apollo_agent):
    """Test finding a person at a company"""
    mock_responses = {
        "organizations/search": MockHTTPResponse({
            "organizations": [{
                "id": "123",
                "name": "Test Company"
            }]
        }),
        "people/search": MockHTTPResponse({
            "people": [{
                "id": "456",
                "name": "John Doe",
                "title": "CEO"
            }]
        })
    }

    mock_client = MockAioHTTPClient(mock_responses)

    with patch('aiohttp.ClientSession', return_value=mock_client):
        result = await apollo_agent.find_company_person("Test Company")
        
        assert result is not None
        assert result["name"] == "John Doe"
        assert result["title"] == "CEO"
        assert result["company"] == "Test Company"

@pytest.mark.asyncio
async def test_get_email(apollo_agent):
    """Test getting email for a person"""
    mock_responses = {
        "people/456/email": MockHTTPResponse({
            "email": "john@example.com"
        })
    }

    mock_client = MockAioHTTPClient(mock_responses)

    with patch('aiohttp.ClientSession', return_value=mock_client):
        email = await apollo_agent.get_email({"id": "456"})
        assert email == "john@example.com"

@pytest.mark.asyncio
async def test_find_company_person_not_found(apollo_agent):
    """Test handling when no person is found"""
    mock_responses = {
        "organizations/search": MockHTTPResponse({
            "organizations": []
        })
    }

    mock_client = MockAioHTTPClient(mock_responses)

    with patch('aiohttp.ClientSession', return_value=mock_client):
        result = await apollo_agent.find_company_person("Test Company")
        assert result is None

@pytest.mark.asyncio
async def test_get_email_not_found(apollo_agent):
    """Test handling when email is not found"""
    mock_responses = {
        "people/456/email": MockHTTPResponse({
            "email": None
        })
    }

    mock_client = MockAioHTTPClient(mock_responses)

    with patch('aiohttp.ClientSession', return_value=mock_client):
        email = await apollo_agent.get_email({"id": "456"})
        assert email is None
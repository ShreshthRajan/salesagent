import pytest
from src.agents.base_agent import BaseAgent
from unittest.mock import AsyncMock

class TestAgent(BaseAgent):
    """Test implementation of BaseAgent"""
    def __init__(self):
        self.find_company_person_called = False
        self.get_email_called = False

    async def find_company_person(self, company_name: str):
        self.find_company_person_called = True
        return {
            "id": "123",
            "name": "Test Person",
            "title": "CEO",
            "company": company_name
        }
    
    async def get_email(self, person_data):
        self.get_email_called = True
        return "test@example.com"

@pytest.mark.asyncio
async def test_base_agent_implementation():
    """Test base agent abstract methods"""
    agent = TestAgent()
    
    # Test find_company_person
    person = await agent.find_company_person("Test Company")
    assert person["name"] == "Test Person"
    assert person["title"] == "CEO"
    assert person["company"] == "Test Company"
    assert agent.find_company_person_called
    
    # Test get_email
    email = await agent.get_email(person)
    assert email == "test@example.com"
    assert agent.get_email_called

@pytest.mark.asyncio
async def test_base_agent_process_success():
    """Test successful processing flow"""
    agent = TestAgent()
    result = await agent.process_company("Test Company")
    
    assert result is not None
    assert result["name"] == "Test Person"
    assert result["email"] == "test@example.com"
    assert result["company"] == "Test Company"
    assert result["title"] == "CEO"

@pytest.mark.asyncio
async def test_base_agent_process_no_person():
    """Test processing when no person found"""
    agent = TestAgent()
    agent.find_company_person = AsyncMock(return_value=None)
    result = await agent.process_company("Test Company")
    assert result is None

@pytest.mark.asyncio
async def test_base_agent_process_no_email():
    """Test processing when no email found"""
    agent = TestAgent()
    agent.get_email = AsyncMock(return_value=None)
    result = await agent.process_company("Test Company")
    assert result is None
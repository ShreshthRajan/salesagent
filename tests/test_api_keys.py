import pytest
import logging
import pytest_asyncio
import aiohttp
from src.utils.config import ConfigManager
from src.utils.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

@pytest_asyncio.fixture
async def config_manager():
    manager = ConfigManager()
    await manager.initialize()
    return manager

async def validate_apollo_key(api_key: str) -> bool:
    async with aiohttp.ClientSession() as session:
        url = "https://api.apollo.io/api/v1/mixed_companies/search"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        data = {
            "q_organization_name": "Apollo",
            "page": 1,
            "per_page": 1
        }
        try:
            async with session.post(url, headers=headers, json=data) as response:
                response_text = await response.text()
                logger.debug(f"Apollo Response Status: {response.status}")
                logger.debug(f"Apollo Response: {response_text}")
                return response.status == 200
        except Exception as e:
            logger.error(f"Apollo API Error: {str(e)}")
            return False



async def validate_rocketreach_key(api_key: str) -> bool:
    """
    Test RocketReach API key by calling a minimal 'search' endpoint.
    Typically returns 201 Created if the key + plan are correct.
    """
    async with aiohttp.ClientSession() as session:
        url = "https://api.rocketreach.co/v2/api/search"  # note "/api/search"
        headers = {
            "Content-Type": "application/json",
            "Api-Key": api_key
        }
        data = {
            "query": {
                "name": ["John Doe"]
            }
        }
        try:
            async with session.post(url, headers=headers, json=data) as response:
                logger.debug(f"RocketReach Response Status: {response.status}")
                # The docs say the search endpoint returns HTTP 201 on success
                # if your plan allows searching.
                return response.status == 201
        except Exception as e:
            logger.error(f"RocketReach API Error: {str(e)}")
            return False


@pytest.mark.asyncio
async def test_apollo_key(config_manager):
    """Check only Apollo key"""
    api_key = config_manager.config.api.apollo.api_key
    assert api_key, "Apollo key missing from environment/config!"

    # Now do your independent test:
    is_valid = await validate_apollo_key(api_key)
    assert is_valid, "Apollo API key is invalid"

@pytest.mark.asyncio
async def test_rocketreach_key(config_manager):
    """Check only RocketReach key"""
    api_key = config_manager.config.api.rocketreach.api_key
    assert api_key, "RocketReach key missing from environment/config!"
    
    # Independent test:
    is_valid = await validate_rocketreach_key(api_key)
    assert is_valid, "RocketReach API key is invalid"

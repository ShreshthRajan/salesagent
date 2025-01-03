# src/agents/rocketreach_agent.py
from typing import Optional, Dict, Any
import logging
from .base_agent import BaseAgent
from src.utils.config import ConfigManager
import aiohttp

logger = logging.getLogger(__name__)

class RocketReachAgent(BaseAgent):
    """RocketReach agent implementation"""
    
    def __init__(self):
        self.config = ConfigManager().config.api.rocketreach
        self.headers = {
            "Content-Type": "application/json",
            "Api-Key": self.config.api_key
        }

    async def find_company_person(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        1) POST /v2/api/search to find a person by (company, title).
        2) Return the first match with an ID.
        """
        logger.info(f"RocketReach: Searching for company: {company_name}")
        
        # Our main search endpoint is POST /v2/api/search. We'll loop over each title
        # until we find a match. 
        url = f"{self.config.base_url}/api/search"  # If base_url ends with '/v2', final is '/v2/api/search'
        
        try:
            async with aiohttp.ClientSession() as session:
                for title in self.TARGET_TITLES:
                    logger.debug(f"RocketReach: Trying title: {title}")
                    
                    # Build the POST body according to the docs
                    body = {
                        "start": 1,
                        "page_size": 1,
                        "query": {
                            "current_employer": [company_name],
                            "current_title": [title]
                        }
                    }
                    
                    async with session.post(url, headers=self.headers, json=body) as response:
                        logger.debug(f"RocketReach: Search status for title '{title}': {response.status}")
                        if response.status != 201:
                            logger.error(
                                f"RocketReach: Search for '{company_name}' + '{title}' failed "
                                f"with status {response.status}"
                            )
                            continue
                        
                        data = await response.json()
                        logger.debug(f"RocketReach: Response data: {data}")

                        # Typically the docs show the result as an array, e.g. data = [{...}, {...}]
                        if not isinstance(data, list) or len(data) == 0:
                            logger.debug(f"RocketReach: No profiles found for title '{title}'")
                            continue
                        
                        profile = data[0]
                        # Each profile has at least an 'id', 'name', 'current_title', etc.
                        # Adapt to actual field names from the doc if needed
                        p_id = profile.get("id")
                        p_name = profile.get("name")
                        p_title = profile.get("current_title")
                        
                        if not p_id:
                            logger.debug(f"RocketReach: Malformed profile for '{title}'")
                            continue
                        
                        logger.info(f"RocketReach: Found person - Name: {p_name}, Title: {p_title}")
                        return {
                            "id": p_id,
                            "name": p_name,
                            "title": p_title,
                            "company": company_name
                        }
                
                logger.info(f"RocketReach: No matching executives found for any title in {company_name}")
                return None
                
        except Exception as e:
            logger.error(f"RocketReach: Error in search: {str(e)}")
            return None

    async def get_email(self, person_data: Dict[str, Any]) -> Optional[str]:
        """
        Use GET /v2/person/lookup?id=xxx to retrieve contact info (emails, phones).
        According to docs, recommended_email or 'emails': [...] might be available.
        """
        logger.info(f"RocketReach: Getting email for person ID: {person_data['id']}")
        
        try:
            async with aiohttp.ClientSession() as session:
                lookup_url = f"{self.config.base_url}/person/lookup"
                params = {"id": person_data["id"]}
                
                async with session.get(lookup_url, headers=self.headers, params=params) as response:
                    logger.debug(f"RocketReach: Email lookup status: {response.status}")
                    if response.status != 200:
                        logger.error(f"RocketReach: Email lookup failed with status {response.status}")
                        return None
                        
                    data = await response.json()
                    logger.debug(f"RocketReach: Email lookup response: {data}")
                    
                    # The final shape might be data["recommended_email"] or data["emails"]
                    # Adjust to match real response shape
                    emails = data.get("emails") or []
                    if emails:
                        logger.info(f"RocketReach: Found email: {emails[0]}")
                        return emails[0]
                    
                    # Or if 'recommended_email' is top-level:
                    # if "recommended_email" in data:
                    #     return data["recommended_email"]
                    
                    logger.info("RocketReach: No email found")
                    return None
                        
        except Exception as e:
            logger.error(f"RocketReach: Error getting email: {str(e)}")
            return None

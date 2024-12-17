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
        """Find C-level executive using RocketReach"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.config.base_url}/api/v2/person/search"
                
                # Try each title until we find someone
                for title in self.TARGET_TITLES:
                    params = {
                        "current_employer": company_name,
                        "current_title": title,
                        "page_size": 1
                    }
                    
                    async with session.get(url, headers=self.headers, params=params) as response:
                        if response.status != 200:
                            continue
                            
                        data = await response.json()
                        profiles = data.get("profiles", [])
                        
                        if profiles:
                            profile = profiles[0]
                            return {
                                "id": profile["id"],
                                "name": profile["name"],
                                "title": profile["current_title"],
                                "company": company_name
                            }
            return None
        except Exception as e:
            logger.error(f"Error in RocketReach search: {str(e)}")
            return None

    async def get_email(self, person_data: Dict[str, Any]) -> Optional[str]:
        """Get email from RocketReach"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.config.base_url}/api/v2/person/lookup"
                params = {"id": person_data["id"]}
                
                async with session.get(url, headers=self.headers, params=params) as response:
                    if response.status != 200:
                        return None
                        
                    data = await response.json()
                    emails = data.get("emails", [])
                    return emails[0] if emails else None
        except Exception as e:
            logger.error(f"Error getting email: {str(e)}")
            return None
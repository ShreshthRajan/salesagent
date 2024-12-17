from typing import Optional, Dict, Any
import logging
from .base_agent import BaseAgent
from src.utils.config import ConfigManager
import aiohttp

logger = logging.getLogger(__name__)

class ApolloAgent(BaseAgent):
    def __init__(self):
        self.config = ConfigManager().config.api.apollo
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}"
        }

    async def find_company_person(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Find C-level executive using Apollo"""
        async with aiohttp.ClientSession() as session:
            # First find company
            async with session.get(
                f"{self.config.base_url}/organizations/search",
                headers=self.headers,
                params={"q_organization_name": company_name}
            ) as response:
                if response.status != 200:
                    return None
                company_data = await response.json()
                orgs = company_data.get("organizations", [])
                if not orgs:
                    return None
                company_id = orgs[0]["id"]

            # Then find person
            async with session.get(
                f"{self.config.base_url}/people/search",
                headers=self.headers,
                params={
                    "organization_ids[]": company_id,
                    "q_keywords": " OR ".join(self.TARGET_TITLES)
                }
            ) as response:
                if response.status != 200:
                    return None
                people_data = await response.json()
                people = people_data.get("people", [])
                if not people:
                    return None
                person = people[0]
                return {
                    "id": person["id"],
                    "name": person["name"],
                    "title": person["title"],
                    "company": company_name
                }

    async def get_email(self, person_data: Dict[str, Any]) -> Optional[str]:
        """Get email from Apollo"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.config.base_url}/people/{person_data['id']}/email",
                headers=self.headers
            ) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                return data.get("email")
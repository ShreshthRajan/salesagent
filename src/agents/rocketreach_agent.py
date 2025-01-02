# src/agents/rocketreach_agent.py
from typing import Optional, Dict, Any
import logging
from .base_agent import BaseAgent
from src.utils.config import ConfigManager
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

def truncate_json(data, max_len=600):
    text = str(data)
    if len(text) > max_len:
        return text[:max_len] + "...(truncated)..."
    return text

class RocketReachAgent(BaseAgent):
    """RocketReach agent implementation"""
    
    def __init__(self):
        self.config = ConfigManager().config.api.rocketreach
        self.headers = {
            "Content-Type": "application/json",
            "Api-Key": self.config.api_key
        }
        # Minimal test titles
        self.TEST_TITLES = [
            "Chief Financial Officer",
            "CFO"
        ]

    async def find_company_person(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        1) POST /v2/api/search with minimal titles
        2) Return first match
        3) Sleep 5s between each attempt to reduce 429s
        """
        logger.info(f"[RocketReach] Searching for '{company_name}' with {len(self.TEST_TITLES)} title(s).")
        url = f"{self.config.base_url}/api/search"

        async with aiohttp.ClientSession() as session:
            for title in self.TEST_TITLES:
                body = {
                    "start": 1,
                    "page_size": 1,
                    "query": {
                        "current_employer": [company_name],
                        "current_title": [title]
                    }
                }
                logger.debug(f"[RocketReach] POST {url} => {body}")
                resp = await session.post(url, headers=self.headers, json=body)
                
                logger.debug(f"[RocketReach] Search status for title='{title}': {resp.status}")
                if resp.status == 429:
                    logger.warning("[RocketReach] Rate-limited (429). Stopping search.")
                    await resp.text()  # read content to close properly
                    return None
                elif resp.status != 201:
                    logger.warning(f"[RocketReach] '{company_name}' + '{title}' => status {resp.status}")
                    await resp.text()  # read content to close
                    # Then sleep to avoid hitting rate-limit again
                    logger.info("[RocketReach] Sleeping 5s to reduce chance of 429...")
                    await asyncio.sleep(5)
                    continue

                data = await resp.json()
                logger.debug(f"[RocketReach] Response data => {truncate_json(data)}")

                if not isinstance(data, list) or len(data) == 0:
                    logger.info(f"[RocketReach] No profiles for title='{title}' with '{company_name}'")
                    # Sleep
                    logger.info("[RocketReach] Sleeping 5s to reduce chance of 429...")
                    await asyncio.sleep(5)
                    continue

                # Found a list of profiles
                profile = data[0]
                p_id = profile.get("id")
                p_name = profile.get("name", "")
                p_title = profile.get("current_title", "")
                p_employer = profile.get("current_employer", "")

                if not p_id:
                    logger.info(f"[RocketReach] No 'id' in profile for title='{title}'")
                    logger.info("[RocketReach] Sleeping 5s to reduce chance of 429...")
                    await asyncio.sleep(5)
                    continue

                # Basic check for employer name
                if company_name.lower() not in p_employer.lower():
                    logger.info(f"[RocketReach] Skipping mismatch employer '{p_employer}'.")
                    logger.info("[RocketReach] Sleeping 5s to reduce chance of 429...")
                    await asyncio.sleep(5)
                    continue

                logger.info(f"[RocketReach] Found => Name='{p_name}', Title='{p_title}'")
                # Sleep here before returning (optional)
                return {
                    "id": p_id,
                    "name": p_name,
                    "title": p_title,
                    "company": company_name
                }

            # If we exit the for-loop, no match
            logger.info(f"[RocketReach] No matching titles found for '{company_name}'")
            return None

    async def get_email(self, person_data: Dict[str, Any]) -> Optional[str]:
        """GET /v2/person/lookup?id=xxx => retrieve email(s)."""
        logger.info(f"[RocketReach] Getting email for ID={person_data['id']}")
        lookup_url = f"{self.config.base_url}/person/lookup"
        params = {"id": person_data["id"]}

        async with aiohttp.ClientSession() as session:
            resp = await session.get(lookup_url, headers=self.headers, params=params)
            logger.debug(f"[RocketReach] Email lookup => status {resp.status}")

            if resp.status != 200:
                logger.warning(f"[RocketReach] Email lookup failed: {resp.status}")
                await resp.text()
                return None

            data = await resp.json()
            logger.debug(f"[RocketReach] Lookup response => {truncate_json(data)}")

            emails = data.get("emails") or []
            if emails:
                logger.info(f"[RocketReach] Found email => {emails[0]}")
                return emails[0]

            logger.info("[RocketReach] No email returned in lookup response")
            return None

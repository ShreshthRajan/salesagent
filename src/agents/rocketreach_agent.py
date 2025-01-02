# src/agents/rocketreach_agent.py
import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any, List

from src.agents.base_agent import BaseAgent
from src.utils.config import ConfigManager

logger = logging.getLogger(__name__)

class RocketReachAgent(BaseAgent):
    """RocketReach agent implementing the base abstract methods + a custom process_company for up to 10 folks."""

    def __init__(self):
        self.config = ConfigManager().config.api.rocketreach
        self.headers = {
            "Content-Type": "application/json",
            "Api-Key": self.config.api_key
        }

    # ========== Abstract #1 ==========
    async def find_company_person(self, company_name: str) -> Optional[Dict[str,Any]]:
        """
        Minimal version to get the SINGLE first match from a search. 
        We'll limit to 1 person in search => returns it or None.
        """
        url = f"{self.config.base_url}/api/search"
        body = {
            "start": 1,
            "page_size": 1,
            "query": {
                "current_employer": [company_name],
            }
        }
        profiles = await self._post_with_retry(url, body)
        if not profiles:
            return None
        return profiles[0]

    # ========== Abstract #2 ==========
    async def get_email(self, person_data: Dict[str,Any]) -> Optional[str]:
        """Use GET /v2/person/lookup?id=xxx => single email or None."""
        pid = person_data.get("id")
        if not pid:
            return None
        return await self._lookup_email(pid)

    # ========== Override for up to 10 employees (any titles) ========== 
    async def process_company(self, company_name: str) -> Optional[Dict[str,Any]]:
        """
        We want up to 10 employees, ignoring titles, + their emails.
        We can do "start=1, page_size=10, query: { 'current_employer': [company_name] }"
        Then do person/lookup for each => gather email. 
        Return { people: [...], emails: [...] } or None
        """
        url = f"{self.config.base_url}/api/search"
        body = {
            "start": 1,
            "page_size": 10,
            "query": {
                "current_employer": [company_name]
            }
        }
        profiles = await self._post_with_retry(url, body)
        if not profiles:
            return None

        # Now get emails
        final_people = []
        final_emails = []
        for prof in profiles:
            pid = prof.get("id")
            if not pid:
                continue
            e = await self._lookup_email(pid)
            person_info = {
                "name": prof.get("name",""),
                "title": prof.get("current_title",""),
                "email": e
            }
            final_people.append(person_info)
            if e:
                final_emails.append(e)

        if not final_emails:
            return None
        return {
            "people": final_people,
            "emails": final_emails
        }

    # ========== Internal helpers ==========

    async def _post_with_retry(self, url: str, json_body: Dict[str,Any]) -> Optional[List[Dict[str,Any]]]:
        """
        Helper for RocketReach POST => parse 429, sleep + retry once.
        If success => return list of profiles, else None.
        """
        async with aiohttp.ClientSession() as session:
            resp = await session.post(url, headers=self.headers, json=json_body)
            if resp.status == 429:
                # parse Retry-After
                retry_secs = float(resp.headers.get("Retry-After","5"))
                logger.warning(f"[RocketReach] 429 => sleeping {retry_secs}s, then retry")
                await asyncio.sleep(retry_secs)

                resp2 = await session.post(url, headers=self.headers, json=json_body)
                if resp2.status == 429:
                    logger.error("[RocketReach] Still 429 after retry => aborting.")
                    await resp2.text()
                    return None
                if resp2.status != 201:
                    logger.warning(f"[RocketReach] post_with_retry => status={resp2.status} after backoff.")
                    await resp2.text()
                    return None
                data2 = await resp2.json()
                if not isinstance(data2, list) or len(data2)==0:
                    return None
                return data2
            elif resp.status != 201:
                logger.warning(f"[RocketReach] post_with_retry => status={resp.status} (no 429).")
                await resp.text()
                return None

            data = await resp.json()
            if not isinstance(data, list) or not data:
                return None
            return data

    async def _lookup_email(self, person_id: str) -> Optional[str]:
        """
        GET /v2/person/lookup?id=xxx with a single 429 retry
        """
        lookup_url = f"{self.config.base_url}/person/lookup"
        params = {"id": person_id}
        async with aiohttp.ClientSession() as session:
            resp = await session.get(lookup_url, headers=self.headers, params=params)
            if resp.status == 429:
                secs = float(resp.headers.get("Retry-After","5"))
                logger.warning(f"[RocketReach] 429 on lookup => sleeping {secs}s")
                await asyncio.sleep(secs)
                resp2 = await session.get(lookup_url, headers=self.headers, params=params)
                if resp2.status == 429:
                    logger.error("[RocketReach] Still 429 after second attempt => abort.")
                    await resp2.text()
                    return None
                if resp2.status != 200:
                    logger.warning(f"[RocketReach] _lookup_email => {resp2.status} after backoff")
                    await resp2.text()
                    return None
                d2 = await resp2.json()
                emails2 = d2.get("emails",[])
                return emails2[0] if emails2 else None
            elif resp.status != 200:
                logger.warning(f"[RocketReach] _lookup_email => {resp.status}")
                await resp.text()
                return None

            data = await resp.json()
            emails = data.get("emails",[])
            return emails[0] if emails else None

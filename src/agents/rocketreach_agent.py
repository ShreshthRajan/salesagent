import logging
import aiohttp
from typing import Optional, Dict, Any, List

from src.agents.base_agent import BaseAgent
from src.utils.config import ConfigManager

logger = logging.getLogger(__name__)

class RocketReachAgent(BaseAgent):
    """
    RocketReach 2-step approach:
      1) POST /v2/api/search => find up to X profiles for a given company + finance titles
      2) For each found person => GET /v2/person/lookup?id=xxx => retrieve email(s)
    """

    def __init__(self):
        self.config = ConfigManager().config.api.rocketreach
        # Typically your base URL ends with /v2, e.g. "https://api.rocketreach.co/v2"
        self.headers = {
            "Content-Type": "application/json",
            "Api-Key": self.config.api_key
        }
        self._domain: Optional[str] = None

    def set_domain(self, domain: str):
        """
        Let the test code set the domain (e.g. "hecla.com") if needed.
        Possibly you won't rely on domain for RocketReach, just a company name.
        """
        self._domain = domain

    async def find_company_person(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        Minimal approach for BaseAgent:
          - do a search for company_name + minimal titles => get 1 person
          - return the first or None
        """
        # We'll choose minimal finance titles
        finance_titles = ["Chief Financial Officer", "CFO"]
        found = await self._search_people(company_name, finance_titles, limit=1)
        if not found:
            return None
        return found[0]

    async def get_email(self, person_data: Dict[str, Any]) -> Optional[str]:
        """
        Single-person email => GET /v2/person/lookup?id=xxx
        """
        pid = person_data.get("id")
        if not pid:
            return None

        lookup_url = f"{self.config.base_url}/person/lookup"
        params = {"id": pid}

        async with aiohttp.ClientSession() as session:
            async with session.get(lookup_url, headers=self.headers, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"[RocketReach] get_email => status={resp.status}")
                    return None

                data = await resp.json()
                emails = data.get("emails") or []
                return emails[0] if emails else None

    async def process_company(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        Full 2-step approach:
          1) search up to 5 or 7 or 10 finance folks
          2) for each found => lookup email => build final results
          returns { "people": [...], "emails": [...] }
        """
        # Let's do, say, up to 5 finance folks
        finance_titles = [
            "Chief Financial Officer", "CFO", 
            "VP Finance", "VP, Finance"
        ]
        found_people = await self._search_people(company_name, finance_titles, limit=5)
        if not found_people:
            logger.info(f"[RocketReach] No matching folks for '{company_name}'.")
            return None

        # For each person => do single-person email lookup
        final_people = []
        revealed_emails = []
        for p in found_people:
            pid = p.get("id")
            name = p.get("name", "")
            title = p.get("current_title", "")
            
            # do the GET /person/lookup
            email = await self.get_email(p)
            # fallback if not found
            if not email:
                email = "email_not_unlocked@domain.com"

            person_info = {
                "name": name,
                "title": title,
                "email": email
            }
            final_people.append(person_info)
            if email and "email_not_unlocked@" not in email:
                revealed_emails.append(email)

        return {
            "people": final_people,
            "emails": revealed_emails
        }

    # -------------------- Step 1: People Search --------------------
    async def _search_people(self, company_name: str, titles: List[str], limit: int) -> List[Dict[str,Any]]:
        """
        POST /v2/api/search => pass something like:
          {
            "start": 1,
            "page_size": limit,
            "query": {
                "current_employer": [company_name],
                "current_title": titles
            }
          }
        Then parse the returned list. 
        If your plan requires a 201 status code for success, handle that check.
        """
        url = f"{self.config.base_url}/api/search"
        body = {
            "start": 1,
            "page_size": limit,
            "query": {
                "current_employer": [company_name],
                # If you want domain-based search, you could do:
                # "company_domain": [self._domain] if self._domain else ...
                "current_title": titles
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=body) as resp:
                # According to docs, a valid search is 201 => "Created"
                # if resp.status != 201 => handle error
                if resp.status != 201:
                    logger.warning(f"[RocketReach] _search_people => status={resp.status}, company={company_name}")
                    return []

                data = await resp.json()
                # Typically we might get an array of profiles or a dict with "profiles": [...]
                if not isinstance(data, list):
                    # sometimes data is a dict => data["profiles"]
                    # handle whichever shape your plan returns
                    profiles = data.get("profiles") or []
                    return profiles

                # else if data is a plain list
                return data

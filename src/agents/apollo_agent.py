import logging
import aiohttp
from typing import Optional, Dict, Any, List

from src.agents.base_agent import BaseAgent
from src.utils.config import ConfigManager

logger = logging.getLogger(__name__)

class ApolloAgent(BaseAgent):
    """
    3-step flow:
      1) /mixed_companies/search => pass both q_organization_name="Hecla Mining Company" 
         and organization_domains=["hecla.com"] to find the exact org_id
      2) /mixed_people/search => pass organization_ids[]=[that org_id], with finance titles
         if <7 found => pass same org_id but no titles => fill to 7
      3) /people/bulk_match?reveal_personal_emails=true => reveal personal emails if plan allows
    Returns partial data if no real emails, so you see at least the correct employees.
    """

    def __init__(self):
        self.config = ConfigManager().config.api.apollo
        self.headers = {
            "Content-Type": "application/json",
            # For most Apollo API keys, x-api-key is correct. If you still get 401, confirm your plan.
            "x-api-key": self.config.api_key
        }

    async def find_company_person(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        Minimal approach:
          1) find org_id
          2) people search => get 1 person
        """
        org_id = await self._find_org_id(company_name)
        if not org_id:
            return None

        people = await self._search_people(org_id=org_id, titles=None, limit=1)
        if not people:
            return None
        return people[0]

    async def get_email(self, person_data: Dict[str, Any]) -> Optional[str]:
        """
        Single-person approach => /people/match
        """
        pid = person_data.get("id")
        if not pid:
            return None

        match_url = f"{self.config.base_url}/people/match"
        body = {
            "person_id": pid,
            "reveal_personal_emails": True
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(match_url, headers=self.headers, json=body) as resp:
                if resp.status != 200:
                    logger.warning(f"[Apollo] get_email => {resp.status}")
                    return None
                data = await resp.json()
                emails = data.get("emails", [])
                return emails[0] if emails else None

    async def process_company(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        3-step:
          (1) /mixed_companies/search => org_id using name+domain
          (2) /mixed_people/search => up to 7 w/ finance titles. If <7, fill from no titles
          (3) /people/bulk_match => reveal personal emails
        """
        org_id = await self._find_org_id(company_name)
        if not org_id:
            logger.info(f"[Apollo] Could not find correct org for '{company_name}'.")
            return None

        # Step 2a: up to 7 finance folks
        finance_people = await self._search_people(org_id, self._finance_titles(), limit=7)
        found_finance = len(finance_people)

        # Step 2b: If fewer than 7, fill from no titles
        if found_finance < 7:
            needed = 7 - found_finance
            more = await self._search_people(org_id, None, needed)
            finance_people.extend(more)

        if not finance_people:
            logger.info(f"[Apollo] No employees found for '{company_name}' (org_id={org_id}).")
            return None

        # Step 3: bulk email reveal
        email_map = await self._bulk_enrich(finance_people)

        # Build final results
        results = []
        real_emails = []
        for p in finance_people:
            pid = p.get("id")
            placeholder = p.get("email")  # possibly "email_not_unlocked@domain.com"
            revealed = email_map.get(pid)  # actual personal email or ""
            final = revealed if revealed else placeholder

            name = p.get("name","")
            title = p.get("title","")

            info = {"name": name, "title": title, "email": final}
            results.append(info)
            if final and "email_not_unlocked@" not in final:
                real_emails.append(final)

        return {
            "people": results,
            "emails": real_emails
        }

    # ---------------------------------------------------------------
    # Step (1) => /mixed_companies/search with both name & domain
    # ---------------------------------------------------------------
    async def _find_org_id(self, company_name: str) -> Optional[str]:
        """
        We combine q_organization_name=company_name and organization_domains=["hecla.com"]
        to match docs: 'Filter search results to a specific company name plus a domain.'
        """
        url = f"{self.config.base_url}/mixed_companies/search"
        body = {
            "q_organization_name": company_name,
            "organization_domains": ["hecla.com"],
            "page": 1,
            "per_page": 1
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=body) as resp:
                if resp.status != 200:
                    logger.warning(f"[Apollo] _find_org_id => status {resp.status}")
                    return None
                data = await resp.json()
                # 'accounts' is typically the array w/ name, domain, org_id
                accounts = data.get("accounts", [])
                if not accounts:
                    logger.info(f"[Apollo] No accounts returned for name='{company_name}' + domain=hecla.com.")
                    return None

                # Many times it's "organization_id"
                acc = accounts[0]
                org_id = acc.get("organization_id")
                if not org_id:
                    logger.warning(f"[Apollo] Missing 'organization_id' in first account => {acc}")
                    return None

                # Optional: Check if the "domain" or "name" matches "hecla.com" or "Hecla Mining"
                # But we'll trust the first account is correct.
                return org_id

    # ---------------------------------------------------------------
    # Step (2) => /mixed_people/search => pass org_id + titles
    # ---------------------------------------------------------------
    async def _search_people(self, org_id: str, titles: Optional[List[str]], limit: int) -> List[Dict[str, Any]]:
        """
        /mixed_people/search: pass 'organization_ids[]=[org_id]' plus 'person_titles[]' if we have them
        'page':1, 'per_page':limit
        returns -> data['people']
        """
        url = f"{self.config.base_url}/mixed_people/search"
        body = {
            "organization_ids[]": [org_id],
            "page": 1,
            "per_page": limit
        }
        if titles:
            body["person_titles[]"] = titles

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=body) as resp:
                if resp.status != 200:
                    logger.warning(f"[Apollo] _search_people => {resp.status}, org_id={org_id}, titles={titles}")
                    return []
                data = await resp.json()
                found = data.get("people", [])
                logger.info(f"[Apollo] Found {len(found)} people (org_id={org_id}, titles={titles}).")
                return found

    # ---------------------------------------------------------------
    # Step (3) => /people/bulk_match?reveal_personal_emails=true
    # ---------------------------------------------------------------
    async def _bulk_enrich(self, people: List[Dict[str,Any]]) -> Dict[str,str]:
        """
        POST => /api/v1/people/bulk_match?reveal_personal_emails=true
        "details": [{ "id": person["id"] }]
        returns -> { pid => email or "" }
        """
        if not people:
            return {}

        url = f"{self.config.base_url}/people/bulk_match?reveal_personal_emails=true"
        details = []
        for p in people:
            pid = p.get("id")
            if pid:
                details.append({"id": pid})

        if not details:
            return {}

        body = {"details": details}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=body) as resp:
                if resp.status != 200:
                    logger.warning(f"[Apollo] _bulk_enrich => {resp.status}")
                    return {}
                data = await resp.json()
                matched = data.get("people", [])
                results = {}
                for m in matched:
                    pid = m.get("id", "")
                    # "emails" might be an array => we take the first
                    emails = m.get("emails") or []
                    best = emails[0] if emails else ""
                    results[pid] = best
                return results

    # ---------------------------------------------------------------
    # Utility: subset of finance titles from BaseAgent
    # ---------------------------------------------------------------
    def _finance_titles(self) -> List[str]:
        return [
            "Chief Financial Officer", "CFO",
            "VP Finance", "VP, Finance",
            "Vice President Finance", "Vice President, Finance",
            "Treasurer", "Controller", "Corporate Controller",
            "Director of Finance", "Head of Finance"
        ]

import logging
import aiohttp
from typing import Optional, Dict, Any, List

from src.agents.base_agent import BaseAgent
from src.utils.config import ConfigManager

logger = logging.getLogger(__name__)

class ApolloAgent(BaseAgent):
    """
    Apollo 3-step approach:
      1) POST /mixed_companies/search => find correct org by name + domain (plus filters)
      2) POST /mixed_people/search => up to 7 employees (finance titles, then fill up)
      3) POST /people/bulk_match?reveal_personal_emails=true => reveal personal emails
    """

    def __init__(self):
        self.config = ConfigManager().config.api.apollo
        self.headers = {
            "Content-Type": "application/json",
            # For your key type, "x-api-key" might be correct:
            "x-api-key": self.config.api_key
        }
        self._domain: Optional[str] = None  # Set externally

    def set_domain(self, domain: str):
        """
        E.g. "hecla.com"
        """
        self._domain = domain

    async def find_company_person(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        Minimal method for BaseAgent:
          1) find org_id by name+domain
          2) fetch 1 person => return first or None
        """
        org_id = await self._find_org_id(company_name)
        if not org_id:
            return None

        # People search, no titles, limit=1
        p_list = await self._search_people(org_id, titles=None, limit=1)
        if not p_list:
            return None

        return p_list[0]

    async def get_email(self, person_data: Dict[str, Any]) -> Optional[str]:
        """
        Single-person enrichment => /people/match (just for BaseAgent compliance).
        """
        pid = person_data.get("id")
        if not pid:
            return None

        url = f"{self.config.base_url}/people/match"
        body = {
            "person_id": pid,
            "reveal_personal_emails": True
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=body) as resp:
                if resp.status != 200:
                    logger.warning(f"[Apollo] get_email => status={resp.status}")
                    return None
                data = await resp.json()
                emails = data.get("emails", [])
                return emails[0] if emails else None

    async def process_company(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        The full 3-step approach:
          1) get org_id from name+domain (with extra filters)
          2) search people => up to 7 finance titles, fill to 7
          3) bulk enrich => reveal personal emails
          returns { "people": [...], "emails": [...] } or None
        """
        if not self._domain:
            logger.error("ApolloAgent: No domain set! Please call set_domain(...) first.")
            return None

        org_id = await self._find_org_id(company_name)
        if not org_id:
            logger.info(f"[Apollo] No org_id found for '{company_name}' + domain='{self._domain}'")
            return None

        # Step A: fetch up to 7 finance folks
        finance_people = await self._search_people(org_id, self._finance_titles(), 7)
        fin_count = len(finance_people)

        # Step B: fill to 7 if needed
        if fin_count < 7:
            leftover = 7 - fin_count
            more = await self._search_people(org_id, titles=None, limit=leftover)
            finance_people.extend(more)

        if not finance_people:
            logger.info(f"[Apollo] No employees found for {company_name} (org_id={org_id}).")
            return None

        # Step C: bulk enrich
        email_map = await self._bulk_enrich(finance_people)

        # Build final results
        final_people = []
        revealed_emails = []
        for p in finance_people:
            pid = p.get("id")
            nm = p.get("name", "")
            ti = p.get("title", "")
            placeholder = p.get("email") or "email_not_unlocked@domain.com"
            real = email_map.get(pid)
            best_email = real if real else placeholder

            person_info = {
                "name": nm,
                "title": ti,
                "email": best_email
            }
            final_people.append(person_info)

            if best_email and "email_not_unlocked@" not in best_email:
                revealed_emails.append(best_email)

        return {
            "people": final_people,
            "emails": revealed_emails
        }

    # ------------------- Step 1: Org Search ------------------------
    async def _find_org_id(self, company_name: str) -> Optional[str]:
        """
        /mixed_companies/search with these filters:
          {
            "q_organization_name": company_name,
            "organization_domains": [self._domain],
            # Possibly more filters:
            #  "organization_num_employees_ranges": ["1000,5000"],
            #  "q_organization_keyword_tags": ["mining"],
            #  "organization_locations": ["idaho"],
            "page": 1,
            "per_page": 5
          }
        We'll pick the first account whose domain==_domain and name ~contains company_name.
        """
        if not self._domain:
            logger.warning("No domain set => cannot find org.")
            return None

        url = f"{self.config.base_url}/mixed_companies/search"
        body = {
            "q_organization_name": company_name,
            "organization_domains": [self._domain],
            "page": 1,
            "per_page": 5
        }
        # OPTIONAL: If you keep getting partial matches, you can add:
        # body["q_organization_keyword_tags"] = ["mining"]
        # body["organization_num_employees_ranges"] = ["500,5000"]
        # body["organization_locations"] = ["idaho"]  # or ["Coeur d'Alene"]

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=body) as resp:
                if resp.status != 200:
                    logger.warning(f"[Apollo] _find_org_id => status={resp.status} for '{company_name}' domain='{self._domain}'")
                    return None
                data = await resp.json()
                accounts = data.get("accounts", [])
                if not accounts:
                    logger.info(f"[Apollo] No accounts returned for '{company_name}' + '{self._domain}'")
                    return None

                c_name_lower = company_name.lower()

                # Step A: find best match
                # We'll pick the account with domain= _domain, name includes c_name_lower
                for acc in accounts:
                    acc_dom = acc.get("domain") or acc.get("primary_domain")
                    acc_name = (acc.get("name") or "").lower()
                    if acc_dom == self._domain and c_name_lower in acc_name:
                        return acc.get("organization_id")

                # Step B: fallback => first
                # Might lead to partial matches
                return accounts[0].get("organization_id")

    # ------------------- Step 2: People Search ---------------------
    async def _search_people(self, org_id: str, titles: Optional[List[str]], limit: int) -> List[Dict[str,Any]]:
        """
        POST /mixed_people/search => pass { "organization_ids[]": [org_id], "person_titles[]": titles?, etc. }
        Possibly you can also pass "person_locations[]": ["idaho"] or "contact_email_status[]":["verified"] 
        to reduce partial results from random geographies.
        """
        url = f"{self.config.base_url}/mixed_people/search"
        body = {
            "organization_ids[]": [org_id],
            "page": 1,
            "per_page": limit
        }
        if titles:
            body["person_titles[]"] = titles

        # OPTIONAL location filter to ensure "coeur d'alene" or "idaho" employees
        # body["person_locations[]"] = ["idaho"]

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=body) as resp:
                if resp.status != 200:
                    logger.warning(f"[Apollo] _search_people => status={resp.status} (org_id={org_id}, titles={titles})")
                    return []
                data = await resp.json()
                found = data.get("people", [])
                logger.info(f"[Apollo] Found {len(found)} people (org_id={org_id}, titles={titles}).")
                return found

    # ------------------- Step 3: Bulk Enrich -----------------------
    async def _bulk_enrich(self, people: List[Dict[str,Any]]) -> Dict[str,str]:
        """
        /people/bulk_match?reveal_personal_emails=true => { "details": [ { "id": p["id"]} ] }
        returns dict => pid -> best_email
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
                    logger.warning(f"[Apollo] _bulk_enrich => status={resp.status}")
                    return {}
                data = await resp.json()
                matched = data.get("people", [])
                res_map = {}
                for m in matched:
                    pid = m.get("id")
                    emails = m.get("emails") or []
                    best = emails[0] if emails else ""
                    res_map[pid] = best
                return res_map

    def _finance_titles(self) -> List[str]:
        """
        Subset of finance/exec titles you want (or re-use from BaseAgent).
        """
        return [
            "Chief Financial Officer",
            "CFO",
            "VP Finance", "VP, Finance",
            "Vice President Finance", "Vice President, Finance",
            "Treasurer", "Controller", "Corporate Controller",
            "Director of Finance", "Head of Finance"
        ]

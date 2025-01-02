# src/agents/apollo_agent.py
from typing import Optional, Dict, Any
import logging
from .base_agent import BaseAgent
from src.utils.config import ConfigManager
import aiohttp

logger = logging.getLogger(__name__)

# Helper function to avoid giant log spam
def truncate_json(data, max_len=600):
    """
    Return a string of JSON-like data truncated to max_len chars
    so logs don't blow up.
    """
    text = str(data)
    if len(text) > max_len:
        return text[:max_len] + "...(truncated)..."
    return text

class ApolloAgent(BaseAgent):
    def __init__(self):
        self.config = ConfigManager().config.api.apollo
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": self.config.api_key,
        }

    async def find_company_person(self, company_name: str) -> Optional[Dict[str, Any]]:
        logger.info(f"[Apollo] Searching for '{company_name}' with domain-based approach.")
        company_url = f"{self.config.base_url}/mixed_companies/search"

        domain_map = {
            "hecla mining company": "hecla.com",
            "hecla mining": "hecla.com",
            "hecla": "hecla.com",
        }
        use_domain = domain_map.get(company_name.lower()) or "hecla.com"

        # Step 1: Search accounts
        company_body = {
            "q_organization_name": company_name,
            "organization_domains": [use_domain],
            "page": 1,
            "per_page": 1
        }

        async with aiohttp.ClientSession() as session:
            logger.debug(f"[Apollo] POST {company_url} => {company_body}")
            async with session.post(company_url, headers=self.headers, json=company_body) as resp:
                logger.debug(f"[Apollo] Company search status: {resp.status}")
                if resp.status != 200:
                    logger.warning(f"[Apollo] Company search failed: {resp.status}")
                    return None

                data = await resp.json()
                logger.debug(f"[Apollo] Company search response: {truncate_json(data)}")

                accounts = data.get("accounts", [])
                if not accounts:
                    logger.info(f"[Apollo] No matching account for '{company_name}' (domain={use_domain})")
                    return None

                acc = accounts[0]
                org_id = acc.get("organization_id")
                if not org_id:
                    logger.warning(f"[Apollo] Missing organization_id in {acc}")
                    return None

                logger.info(f"[Apollo] Found org_id={org_id} for '{company_name}'.")

            # Step 2: Search people
            people_url = f"{self.config.base_url}/mixed_people/search"
            people_body = {
                "organization_ids": [org_id],
                "q_title": self._combine_titles_for_or_search(),
                "page": 1,
                "per_page": 10
            }

            logger.debug(f"[Apollo] POST {people_url} => {people_body}")
            async with session.post(people_url, headers=self.headers, json=people_body) as resp:
                logger.debug(f"[Apollo] Person search status: {resp.status}")
                if resp.status != 200:
                    logger.warning(f"[Apollo] Person search failed: {resp.status}")
                    return None

                people_data = await resp.json()
                logger.debug(f"[Apollo] Person search response: {truncate_json(people_data)}")

                found_people = people_data.get("people") or []
                if not found_people:
                    logger.info(f"[Apollo] No matching exec in org {org_id}")
                    return None

                person = found_people[0]
                logger.info(f"[Apollo] Found person => {person['name']} (title={person['title']})")
                return {
                    "id": person["id"],
                    "name": person["name"],
                    "title": person["title"],
                    "company": company_name
                }

    async def get_email(self, person_data: Dict[str, Any]) -> Optional[str]:
        logger.info(f"[Apollo] Enriching email for person ID={person_data['id']}")
        match_url = f"{self.config.base_url}/people/match"
        body = {
            "person_id": person_data["id"],
            "reveal_personal_emails": True
        }

        async with aiohttp.ClientSession() as session:
            logger.debug(f"[Apollo] POST {match_url} => {body}")
            async with session.post(match_url, headers=self.headers, json=body) as resp:
                logger.debug(f"[Apollo] Enrichment status: {resp.status}")
                if resp.status != 200:
                    logger.warning(f"[Apollo] Enrichment failed: {resp.status}")
                    return None

                data = await resp.json()
                logger.debug(f"[Apollo] Enrichment response: {truncate_json(data)}")

                emails = data.get("emails", [])
                if emails:
                    logger.info(f"[Apollo] Found email => {emails[0]}")
                    return emails[0]

                logger.info("[Apollo] No email found in enrichment response")
                return None

    def _combine_titles_for_or_search(self) -> str:
        # keep it short for the example
        relevant_titles = [
            "Chief Financial Officer", "CFO",
            "VP Finance", "Vice President, Finance"
        ]
        return " OR ".join([f'"{t}"' for t in relevant_titles])

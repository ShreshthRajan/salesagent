# src/agents/apollo_agent.py
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
            "x-api-key": self.config.api_key  # <-- Apollo now prefers x-api-key
        }
        # If your actual key still works with "Authorization: Bearer ...", keep that.
        # But many docs show "x-api-key: <KEY>"

    async def find_company_person(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Search for a company, then find a C-level exec using 'mixed_people/search'."""
        logger.info(f"Apollo: Searching for company: {company_name}")
        
        # 1) Find the company via POST /api/v1/mixed_companies/search
        company_url = f"{self.config.base_url}/mixed_companies/search"
        company_body = {
            "q_organization_name": company_name,
            "page": 1,
            "per_page": 1
        }
        
        async with aiohttp.ClientSession() as session:
            logger.debug(f"Apollo: Posting to {company_url} with {company_body}")
            async with session.post(company_url, headers=self.headers, json=company_body) as response:
                logger.debug(f"Apollo: Company search status: {response.status}")
                if response.status != 200:
                    logger.error(f"Apollo: Company search failed with status {response.status}")
                    return None
                
                company_data = await response.json()
                # According to Apollo docs, the returned array/list may live under "companies" or "organizations"
                orgs = company_data.get("companies") or company_data.get("organizations") or []
                if not orgs:
                    logger.info(f"Apollo: No company found matching '{company_name}'")
                    return None
                
                org_id = orgs[0]["id"]
                logger.info(f"Apollo: Found company ID: {org_id}")

            # 2) Find person(s) by calling POST /api/v1/mixed_people/search
            people_url = f"{self.config.base_url}/mixed_people/search"
            # Build a single query for the known titles. 
            # Alternatively, loop over titles, but here's one call with a broad OR.
            people_body = {
                "organization_ids": [org_id],
                "page": 1,
                "per_page": 10,
                "q_title": self._combine_titles_for_or_search()
            }

            logger.debug(f"Apollo: Posting to {people_url} with {people_body}")
            async with session.post(people_url, headers=self.headers, json=people_body) as response:
                logger.debug(f"Apollo: Person search status: {response.status}")
                if response.status != 200:
                    logger.error(f"Apollo: Person search failed with status {response.status}")
                    return None
                
                people_data = await response.json()
                # Usually the results might be under "people" or "contacts"
                found_people = people_data.get("people") or []
                if not found_people:
                    logger.info("Apollo: No matching executives found")
                    return None
                
                person = found_people[0]
                logger.info(f"Apollo: Found person - Name: {person['name']}, Title: {person['title']}")
                return {
                    "id": person["id"],
                    "name": person["name"],
                    "title": person["title"],
                    "company": company_name
                }

    async def get_email(self, person_data: Dict[str, Any]) -> Optional[str]:
        """
        Use the People Enrichment endpoint to reveal an email.
        POST /api/v1/people/match with e.g.:
          {
            "person_id": <person_data['id']>,
            "reveal_personal_emails": true
          }
        """
        logger.info(f"Apollo: Enriching email for person ID: {person_data['id']}")
        
        match_url = f"{self.config.base_url}/people/match"
        body = {
            "person_id": person_data["id"],
            "reveal_personal_emails": True,
            # If you want phone:
            # "reveal_phone_number": True
        }
        
        async with aiohttp.ClientSession() as session:
            logger.debug(f"Apollo: Posting to {match_url} with {body}")
            async with session.post(match_url, headers=self.headers, json=body) as response:
                logger.debug(f"Apollo: Email enrichment status: {response.status}")
                if response.status != 200:
                    logger.error(f"Apollo: Enrichment failed with status {response.status}")
                    return None
                
                data = await response.json()
                # The docs say you might get "emails": ["john@doe.com"] or similar
                # or "email" or "best_email". Adjust to actual shape:
                emails = data.get("emails", [])
                if emails:
                    # Return first found
                    logger.info(f"Apollo: Found email {emails[0]}")
                    return emails[0]
                
                logger.info("Apollo: No email found in enrichment response")
                return None

    def _combine_titles_for_or_search(self) -> str:
        """
        Helper to combine the titles from BaseAgent into a single OR string,
        e.g. 'CEO OR CFO OR "Vice President Finance" OR ...'
        """
        # For multi-word titles, you might want to quote them or handle them carefully
        # This is a rough example. 
        return " OR ".join([f'"{title}"' if " " in title else title for title in self.TARGET_TITLES])

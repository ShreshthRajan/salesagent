# src/agents/apollo_agent.py
import logging
import aiohttp
import json
from typing import Optional, Dict, Any, List, Tuple
from src.agents.base_agent import BaseAgent
from src.utils.config import ConfigManager

logger = logging.getLogger(__name__)

class ApolloAgent(BaseAgent):
    def __init__(self):
        self.config = ConfigManager().config.api.apollo
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": self.config.api_key
        }
        self._domain: Optional[str] = None
        
    def set_domain(self, domain: str):
        """Set company domain for search"""
        self._domain = domain.lower().strip()
        logger.debug(f"Apollo: Set domain to {self._domain}")

    async def process_company(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Main processing method"""
        if not self._domain:
            logger.error("Apollo: Domain not set. Call set_domain() first.")
            return None

        try:
            logger.debug(f"Apollo: Starting search for {company_name} with domain {self._domain}")
            
            # Step 1: Get organization ID
            org_id = await self._find_org_id(company_name)
            if not org_id:
                logger.info(f"Apollo: No organization found for {company_name}")
                return None
            logger.debug(f"Apollo: Found org_id: {org_id}")

            # Step 2: Find target people
            people = await self._find_target_people(org_id)
            if not people:
                logger.info(f"Apollo: No target people found for {company_name}")
                return None
            logger.debug(f"Apollo: Found {len(people)} target people")

            # Step 3: Bulk enrich for emails
            found_people, pending_people = await self._process_people(people, company_name)
            logger.debug(f"Apollo: Found {len(found_people)} people with emails, {len(pending_people)} pending")

            return {
                "found_people": found_people,
                "pending_people": pending_people,
                "company": company_name,
                "domain": self._domain
            }

        except Exception as e:
            logger.error(f"Apollo error processing {company_name}: {str(e)}")
            return None

    async def _find_org_id(self, company_name: str) -> Optional[str]:
        """Find organization ID using domain + name"""
        try:
            url = f"{self.config.base_url}/mixed_companies/search"
            # Add more specific search parameters
            body = {
                "q_organization_name": company_name,
                "organization_domains": [self._domain],
                # Filter by website to ensure accuracy
                "q_organization_website": self._domain,
                "page": 1,
                "per_page": 10  # Get more results to find exact match
            }
            
            logger.debug(f"Apollo: Searching for company with params: {json.dumps(body)}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=body) as resp:
                    if resp.status != 200:
                        logger.error(f"Apollo: Company search failed with status {resp.status}")
                        response_text = await resp.text()
                        logger.error(f"Apollo: Error response: {response_text}")
                        return None
                        
                    data = await resp.json()
                    logger.debug(f"Apollo: Company search response: {json.dumps(data)}")
                    accounts = data.get("accounts", [])
                    
                    if not accounts:
                        logger.info("Apollo: No accounts found")
                        return None

                    # Strict matching - normalize names for comparison
                    company_name_normalized = company_name.lower().replace("company", "").strip()
                    domain_normalized = self._domain.lower().strip()

                    # First try exact domain and name match
                    for acc in accounts:
                        acc_domain = acc.get("domain", "").lower().strip()
                        acc_name = acc.get("name", "").lower().replace("company", "").strip()
                        
                        if acc_domain == domain_normalized and \
                           (acc_name == company_name_normalized or \
                            company_name_normalized in acc_name or \
                            acc_name in company_name_normalized):
                            org_id = acc.get("organization_id")
                            logger.info(f"Apollo: Found exact match with org_id {org_id}")
                            return org_id

                    # If no exact match, try looser domain match but require name match
                    for acc in accounts:
                        acc_domain = acc.get("domain", "").lower().strip()
                        acc_name = acc.get("name", "").lower().replace("company", "").strip()
                        
                        if (domain_normalized in acc_domain or acc_domain in domain_normalized) and \
                           (acc_name == company_name_normalized or \
                            company_name_normalized in acc_name or \
                            acc_name in company_name_normalized):
                            org_id = acc.get("organization_id")
                            logger.info(f"Apollo: Found partial match with org_id {org_id}")
                            return org_id
                            
                    logger.info("Apollo: No matching organization found")
                    return None

        except Exception as e:
            logger.error(f"Apollo: Error in org search: {str(e)}")
            return None
        
    async def _find_target_people(self, org_id: str) -> List[Dict[str, Any]]:
        """Find people with target finance titles"""
        try:
            url = f"{self.config.base_url}/mixed_people/search"
            body = {
                "organization_ids[]": [org_id],
                "person_titles[]": self.TARGET_TITLES[:10],  # Use more titles
                # Add filters for better results
                "person_locations[]": ["united states"],  # Focus on US employees
                "contact_email_status[]": ["verified"],  # Only verified emails
                "current_employer_only": True,  # Only current employees
                "page": 1,
                "per_page": 25  # Get more results to find key people
            }
            
            logger.debug(f"Apollo: Searching for people with params: {json.dumps(body)}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=body) as resp:
                    if resp.status != 200:
                        logger.error(f"Apollo: People search failed with status {resp.status}")
                        response_text = await resp.text()
                        logger.error(f"Apollo: Error response: {response_text}")
                        return []
                        
                    data = await resp.json()
                    logger.debug(f"Apollo: People search response: {json.dumps(data)}")
                    all_people = data.get("people", [])
                    
                    # Add strict filtering
                    current_people = []
                    for person in all_people:
                        # Verify current employment
                        current_employer = person.get("current_employer", "").lower()
                        if not (current_employer and 
                               (self._domain in current_employer or 
                                current_employer in self._domain)):
                            continue
                            
                        # Verify location (prefer US/Canada)
                        location = person.get("location", "").lower()
                        if not ("united states" in location or 
                                "us" in location or 
                                "canada" in location or
                                "idaho" in location):  # Hecla is based in Idaho
                            continue
                            
                        current_people.append(person)
                    
                    filtered_people = self._filter_target_people(current_people)
                    logger.info(f"Apollo: Found {len(filtered_people)} matching people after strict filtering")
                    return filtered_people

        except Exception as e:
            logger.error(f"Apollo: Error in people search: {str(e)}")
            return []
        
    async def _process_people(self, people: List[Dict[str, Any]], 
                            company_name: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Process people through bulk enrichment"""
        if not people:
            return [], []

        try:
            url = f"{self.config.base_url}/people/bulk_match"
            details = [{"id": p["id"]} for p in people if p.get("id")]
            
            body = {
                "details": details,
                "reveal_personal_emails": True
            }
            
            logger.debug(f"Apollo: Enriching people with params: {json.dumps(body)}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=body) as resp:
                    if resp.status != 200:
                        logger.error(f"Apollo: Bulk enrichment failed with status {resp.status}")
                        response_text = await resp.text()
                        logger.error(f"Apollo: Error response: {response_text}")
                        return [], people
                        
                    data = await resp.json()
                    logger.debug(f"Apollo: Enrichment response: {json.dumps(data)}")
                    matches = data.get("matched", [])

                    found_people = []
                    pending_people = []
                    
                    email_map = {}
                    for match in matches:
                        pid = match.get("id")
                        emails = match.get("email_status", [])
                        if pid and emails:
                            email_map[pid] = emails[0]
                            logger.debug(f"Apollo: Found email for person {pid}")

                    for person in people:
                        person_data = self._format_person(person, company_name)
                        
                        if person_data["id"] in email_map:
                            person_data["email"] = email_map[person_data["id"]]
                            found_people.append(person_data)
                            logger.debug(f"Apollo: Added person with email: {person_data['name']}")
                        else:
                            pending_people.append(person_data)
                            logger.debug(f"Apollo: Added pending person: {person_data['name']}")

                    return found_people, pending_people

        except Exception as e:
            logger.error(f"Apollo: Error in bulk enrichment: {str(e)}")
            return [], people

    def _filter_target_people(self, people: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter and prioritize people based on title"""
        priority_titles = {
            "CFO": 1, "Chief Financial Officer": 1,
            "CEO": 2, "Chief Executive Officer": 2,
            "VP Finance": 3, "Vice President Finance": 3,
            "VP, Finance": 3, "Vice President, Finance": 3,
            "Controller": 4, "Corporate Controller": 4,
            "Director of Finance": 5, "Head of Finance": 5
        }
        
        def get_priority(person: Dict[str, Any]) -> int:
            title = person.get("title", "").strip()
            return priority_titles.get(title, 999)

        valid_people = [p for p in people if p.get("id") and p.get("title")]
        valid_people.sort(key=get_priority)
        
        return valid_people[:5]

    def _format_person(self, person: Dict[str, Any], company_name: str) -> Dict[str, Any]:
        """Format person data consistently"""
        return {
            "id": person.get("id"),
            "name": person.get("name", ""),
            "title": person.get("title", ""),
            "company": company_name
        }

    # Implement abstract methods
    async def find_company_person(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Implementation of abstract method"""
        if not self._domain:
            logger.error("Apollo: Domain not set for find_company_person")
            return None

        try:
            org_id = await self._find_org_id(company_name)
            if not org_id:
                return None

            people = await self._find_target_people(org_id)
            if not people:
                return None

            return self._format_person(people[0], company_name)

        except Exception as e:
            logger.error(f"Apollo error in find_company_person: {str(e)}")
            return None

    async def get_email(self, person_data: Dict[str, Any]) -> Optional[str]:
        """Implementation of abstract method"""
        try:
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
                        return None
                    data = await resp.json()
                    emails = data.get("person", {}).get("email_status", [])
                    return emails[0] if emails else None

        except Exception as e:
            logger.error(f"Apollo error in get_email: {str(e)}")
            return None
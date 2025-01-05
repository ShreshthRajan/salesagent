# src/agents/rocketreach_agent.py
import logging
import aiohttp
import json
from typing import Optional, Dict, Any, List
from src.agents.base_agent import BaseAgent
from src.utils.config import ConfigManager

logger = logging.getLogger(__name__)

class RocketReachAgent(BaseAgent):
    def __init__(self):
        self.config = ConfigManager().config.api.rocketreach
        self.headers = {
            "Content-Type": "application/json",
            "Api-Key": self.config.api_key
        }

    async def find_company_person(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Implementation of abstract method"""
        try:
            logger.debug(f"RocketReach: Searching for person at {company_name}")
            url = f"{self.config.base_url}/api/search"
            
            # Try each title until we find a match
            for title in self.TARGET_TITLES:
                body = {
                    "start": 1,
                    "page_size": 1,
                    "query": {
                        "current_employer": [company_name],
                        "current_title": [title]
                    }
                }
                
                logger.debug(f"RocketReach: Searching with title '{title}'")
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=self.headers, json=body) as resp:
                        if resp.status != 201:
                            logger.debug(f"RocketReach: Search failed with status {resp.status}")
                            continue
                            
                        data = await resp.json()
                        logger.debug(f"RocketReach: Search response: {json.dumps(data)}")
                        profiles = data.get("profiles", [])
                        
                        if profiles and self._is_valid_profile(profiles[0], company_name):
                            person = self._format_profile(profiles[0])
                            logger.info(f"RocketReach: Found person {person['name']}")
                            return person
                            
            logger.info(f"RocketReach: No matching person found at {company_name}")
            return None

        except Exception as e:
            logger.error(f"RocketReach error in find_company_person: {str(e)}")
            return None

    async def get_email(self, person_data: Dict[str, Any]) -> Optional[str]:
        """Implementation of abstract method"""
        try:
            pid = person_data.get("id")
            if not pid:
                logger.debug("RocketReach: No person ID provided for email lookup")
                return None

            logger.debug(f"RocketReach: Looking up email for person {pid}")
            url = f"{self.config.base_url}/person/lookup"
            params = {"id": pid}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params) as resp:
                    if resp.status != 200:
                        logger.debug(f"RocketReach: Email lookup failed with status {resp.status}")
                        return None
                        
                    data = await resp.json()
                    logger.debug(f"RocketReach: Lookup response: {json.dumps(data)}")
                    
                    # Try professional email first
                    if "professional_emails" in data:
                        emails = data["professional_emails"]
                        if emails:
                            logger.info(f"RocketReach: Found professional email for {person_data.get('name')}")
                            return emails[0]
                    
                    # Then try personal email
                    if "personal_emails" in data:
                        emails = data["personal_emails"]
                        if emails:
                            logger.info(f"RocketReach: Found personal email for {person_data.get('name')}")
                            return emails[0]
                            
                    logger.debug(f"RocketReach: No email found for {person_data.get('name')}")
                    return None

        except Exception as e:
            logger.error(f"RocketReach error in get_email: {str(e)}")
            return None

    async def process_company(self, company_name: str, 
                            pending_people: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        """Enhanced company processing method"""
        try:
            found_people = []
            logger.debug(f"RocketReach: Processing company {company_name}")
            
            # Step 1: Process pending people from Apollo if provided
            if pending_people:
                logger.debug(f"RocketReach: Processing {len(pending_people)} pending people from Apollo")
                for person in pending_people:
                    logger.debug(f"RocketReach: Looking up {person.get('name')}")
                    rr_profile = await self._find_person_by_name(
                        person.get("name", ""),
                        company_name,
                        person.get("title", "")
                    )
                    
                    if rr_profile:
                        email = await self.get_email(rr_profile)
                        if email:
                            person_data = person.copy()
                            person_data["email"] = email
                            found_people.append(person_data)
                            logger.info(f"RocketReach: Found email for pending person {person.get('name')}")
                
            # Step 2: If no results, search for new people
            if not found_people:
                logger.debug("RocketReach: No results from pending people, searching new")
                found_people = await self._search_company_people(company_name)
            
            if found_people:
                logger.info(f"RocketReach: Found {len(found_people)} people with emails")
                return {
                    "found_people": found_people,
                    "company": company_name
                }
            
            logger.info(f"RocketReach: No results found for {company_name}")    
            return None

        except Exception as e:
            logger.error(f"RocketReach error processing {company_name}: {str(e)}")
            return None

    async def _find_person_by_name(self, name: str, company: str, title: str) -> Optional[Dict[str, Any]]:
        """Find person by name + company + title"""
        try:
            logger.debug(f"RocketReach: Searching for {name} at {company}")
            url = f"{self.config.base_url}/api/search"
            body = {
                "start": 1,
                "page_size": 3,
                "query": {
                    "current_employer": [company],
                    "name": name
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=body) as resp:
                    if resp.status != 201:
                        logger.debug(f"RocketReach: Search failed with status {resp.status}")
                        return None
                        
                    data = await resp.json()
                    logger.debug(f"RocketReach: Search response: {json.dumps(data)}")
                    profiles = data.get("profiles", [])
                    
                    # Try to find exact match first
                    for profile in profiles:
                        if self._is_matching_profile(profile, name, company, title):
                            logger.info(f"RocketReach: Found exact match for {name}")
                            return self._format_profile(profile)
                    
                    # Fallback to first profile if it's close enough
                    if profiles:
                        profile = profiles[0]
                        if self._is_similar_profile(profile, name, company):
                            logger.info(f"RocketReach: Found similar match for {name}")
                            return self._format_profile(profile)
                    
                    logger.debug(f"RocketReach: No match found for {name}")
                    return None

        except Exception as e:
            logger.error(f"RocketReach: Error finding person {name}: {str(e)}")
            return None

    async def _search_company_people(self, company_name: str) -> List[Dict[str, Any]]:
        """Search for new people at company"""
        found_people = []
        try:
            # Try each title until we find people
            for title in self.TARGET_TITLES[:5]:  # Try top 5 titles
                logger.debug(f"RocketReach: Searching {company_name} for title '{title}'")
                url = f"{self.config.base_url}/api/search"
                body = {
                    "start": 1,
                    "page_size": 2,
                    "query": {
                        "current_employer": [company_name],
                        "current_title": [title]
                    }
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=self.headers, json=body) as resp:
                        if resp.status != 201:
                            logger.debug(f"RocketReach: Search failed with status {resp.status}")
                            continue
                            
                        data = await resp.json()
                        logger.debug(f"RocketReach: Search response: {json.dumps(data)}")
                        profiles = data.get("profiles", [])
                        
                        for profile in profiles:
                            if not self._is_valid_profile(profile, company_name):
                                continue
                                
                            person_data = self._format_profile(profile)
                            email = await self.get_email(person_data)
                            
                            if email:
                                person_data["email"] = email
                                found_people.append(person_data)
                                logger.info(f"RocketReach: Found person with email: {person_data['name']}")
                                
                            if len(found_people) >= 3:
                                return found_people
                                
        except Exception as e:
            logger.error(f"RocketReach: Error searching company {company_name}: {str(e)}")
            
        return found_people

    def _is_matching_profile(self, profile: Dict[str, Any], name: str, company: str, title: str) -> bool:
        """Verify exact profile match"""
        if not self._is_valid_profile(profile, company):
            return False
            
        profile_name = profile.get("name", "").lower()
        profile_title = profile.get("current_title", "").lower()
        
        name = name.lower()
        title = title.lower()
        
        # Check name similarity (allow partial matches)
        name_parts = name.split()
        profile_parts = profile_name.split()
        name_match = all(part in profile_name for part in name_parts) or \
                    all(part in name for part in profile_parts)
                    
        # Check title similarity
        title_match = title in profile_title or profile_title in title
        
        return name_match and title_match

    def _is_similar_profile(self, profile: Dict[str, Any], name: str, company: str) -> bool:
        """Verify if profile is similar enough"""
        if not self._is_valid_profile(profile, company):
            return False
            
        profile_name = profile.get("name", "").lower()
        name = name.lower()
        
        # Check if either first or last name matches
        name_parts = name.split()
        profile_parts = profile_name.split()
        
        return any(part in profile_name for part in name_parts) or \
               any(part in name for part in profile_parts)

    def _is_valid_profile(self, profile: Dict[str, Any], company: str) -> bool:
        """Validate basic profile data"""
        if not profile.get("id") or not profile.get("name"):
            return False
            
        # Verify company match
        curr_employer = profile.get("current_employer", "").lower()
        company = company.lower()
        
        return company in curr_employer or curr_employer in company

    def _format_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Format profile data consistently"""
        return {
            "id": profile.get("id"),
            "name": profile.get("name"),
            "title": profile.get("current_title"),
            "company": profile.get("current_employer")
        }
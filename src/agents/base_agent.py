from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class BaseAgent(ABC):
    """Base agent for all data source agents"""
    
    TARGET_TITLES = [
        # C-Level
        "CEO", "Chief Executive Officer",
        "CFO", "Chief Financial Officer",
        "President",
        
        # VP Level Finance
        "SVP, CFO", "EVP, CFO",
        "VP Finance", "VP, Finance",
        "VP Treasury", "VP, Treasury",
        "VP Financial", "VP, Financial",
        "Vice President Finance",
        "Vice President, Finance",
        "VP Finance and Corporate Controller",
        "VP, Treasurer",
        "VP, Treasury and Finance",
        
        # Director Level
        "Director of Finance",
        "Director of Accounting",
        "Financial Director",
        "Head of Finance",
        "Head of Financial",
        
        # Other Finance Titles
        "Controller",
        "Corporate Controller",
        "Treasurer",
        "Head of FP&A",
        "Financial Controller"
    ]

    @abstractmethod
    async def find_company_person(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Find target person in a company"""
        pass

    @abstractmethod
    async def get_email(self, person_data: Dict[str, Any]) -> Optional[str]:
        """Get email for a found person"""
        pass

    async def process_company(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Main processing method for a company"""
        try:
            person = await self.find_company_person(company_name)
            if not person:
                return None

            email = await self.get_email(person)
            if email:
                return {
                    "company": company_name,
                    "name": person.get("name"),
                    "title": person.get("title"),
                    "email": email
                }
            return None
        except Exception as e:
            logger.error(f"Error processing company {company_name}: {str(e)}")
            return None
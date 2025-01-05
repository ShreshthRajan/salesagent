"""
src/agents/apollo_autonomous_agent.py
Enhanced autonomous agent for Apollo.io web interactions
"""
from typing import List, Dict, Optional, Tuple
import asyncio
import logging
from datetime import datetime, timedelta
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
import random

from src.services.vision_service import VisionService
from src.services.action_parser import ActionParser
from src.services.navigation_state import NavigationState, NavigationStateMachine
from src.services.validation_service import ValidationService
from src.services.screenshot_pipeline import ScreenshotPipeline
from src.utils.exceptions import AutomationError, ValidationError

logger = logging.getLogger(__name__)

class ApolloAutonomousAgent:
    """Autonomous agent for handling Apollo.io interactions"""
    
    # Target job titles that indicate relevant contacts
    TARGET_TITLES = {
        "Chief Executive Officer",
        "CEO",
        "Chief Financial Officer",
        "CFO",
        "Director of Finance",
        "Director of FP&A",
    }
    
    def __init__(
        self,
        page: Page,
        vision_service: VisionService,
        action_parser: ActionParser,
        state_machine: NavigationStateMachine,
        validation_service: ValidationService,
        screenshot_pipeline: ScreenshotPipeline,
    ):
        self.page = page
        self.vision_service = vision_service
        self.action_parser = action_parser
        self.state_machine = state_machine
        self.validation_service = validation_service
        self.screenshot_pipeline = screenshot_pipeline
        
        # Initialize rate limiting
        self.last_search = datetime.min
        self.last_reveal = datetime.min
        self.search_delay = timedelta(seconds=2)
        self.reveal_delay = timedelta(seconds=1)
        self.action_delay = timedelta(milliseconds=500)
        
        # Initialize state
        self.current_results = []
        self.extracted_contacts = []
        self.error_count = 0
        self.max_errors = 3

    async def login(self, email: str, password: str) -> bool:
        """Handle Apollo.io login with anti-detection measures"""
        try:
            # Random initial delay
            await asyncio.sleep(random.uniform(1, 3))
            
            # Navigate to login page
            await self.page.goto("https://app.apollo.io/")
            await self._wait_with_random_delay(1, 2)
            
            # Click login button using vision service
            login_screen = await self.screenshot_pipeline.capture_optimized()
            login_action = await self.vision_service.analyze_screenshot(login_screen)
            
            if "login" in login_action["page_state"].lower():
                # Find and click login button
                login_button = await self.page.get_by_role("button", name="Log In")
                await login_button.click()
                await self._wait_with_random_delay(1, 2)
                
                # Fill credentials with human-like delays
                await self._type_with_random_delays(
                    'input[type="email"]',
                    email,
                    delay_range=(0.1, 0.3)
                )
                await self._wait_with_random_delay(0.5, 1)
                
                await self._type_with_random_delays(
                    'input[type="password"]',
                    password,
                    delay_range=(0.1, 0.3)
                )
                await self._wait_with_random_delay(0.5, 1)
                
                # Click submit and wait for navigation
                await self.page.click('button[type="submit"]')
                await self.page.wait_for_load_state("networkidle")
                
                # Verify login success
                return await self._verify_login()
                
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            raise AutomationError(f"Failed to login to Apollo.io: {str(e)}")
            
        return False

    async def search_company(self, company_name: str) -> List[Dict]:
        """Search for company and extract relevant contacts"""
        try:
            # Respect rate limits
            await self._wait_for_rate_limit("search")
            
            # Navigate to search interface
            await self._navigate_to_search()
            
            # Enter company search
            await self._type_with_random_delays(
                'input[placeholder="Search"]',
                company_name,
                delay_range=(0.1, 0.2)
            )
            
            # Wait for and click company in dropdown
            await self.page.wait_for_selector(".company-dropdown-item")
            await self._wait_with_random_delay(0.5, 1)
            await self.page.click(f'.company-dropdown-item:has-text("{company_name}")')
            
            # Sort by job title
            await self._sort_results()
            
            # Extract matching contacts
            return await self._extract_matching_contacts()
            
        except Exception as e:
            logger.error(f"Company search failed: {str(e)}")
            raise AutomationError(f"Failed to search company: {str(e)}")

    async def _navigate_to_search(self):
        """Navigate to search interface with anti-detection measures"""
        try:
            # Click search icon
            await self.page.click('button[aria-label="Search"]')
            await self._wait_with_random_delay(0.5, 1)
            
            # Click People section
            await self.page.click('a:has-text("People")')
            await self._wait_with_random_delay(0.5, 1)
            
            # Click Company tab
            await self.page.click('button:has-text("Company")')
            await self.page.wait_for_load_state("networkidle")
            
        except Exception as e:
            logger.error(f"Navigation failed: {str(e)}")
            raise AutomationError(f"Failed to navigate to search: {str(e)}")

    async def _sort_results(self):
        """Sort results by job title"""
        try:
            # Click sort dropdown
            await self.page.click('button[aria-label="Sort"]')
            await self._wait_with_random_delay(0.3, 0.7)
            
            # Select ascending sort
            await self.page.click('button:has-text("Sort ascending")')
            await self.page.wait_for_load_state("networkidle")
            
        except Exception as e:
            logger.error(f"Sort failed: {str(e)}")
            raise AutomationError(f"Failed to sort results: {str(e)}")

    async def _extract_matching_contacts(self) -> List[Dict]:
        """Extract contacts with matching titles"""
        contacts = []
        page_num = 1
        
        while True:
            try:
                # Get current page contacts
                rows = await self.page.query_selector_all("tr.contact-row")
                
                for row in rows:
                    title = await row.query_selector(".job-title")
                    if not title:
                        continue
                        
                    title_text = await title.inner_text()
                    if self._is_target_title(title_text):
                        contact = await self._extract_contact_info(row)
                        if contact:
                            contacts.append(contact)
                
                # Check for next page
                next_button = await self.page.query_selector('button[aria-label="Next"]')
                if not next_button or await next_button.is_disabled():
                    break
                    
                # Go to next page
                await next_button.click()
                await self.page.wait_for_load_state("networkidle")
                page_num += 1
                
            except Exception as e:
                logger.error(f"Extraction failed on page {page_num}: {str(e)}")
                break
                
        return contacts

    def _is_target_title(self, title: str) -> bool:
        """Check if job title matches target titles"""
        title = title.lower()
        return any(target.lower() in title for target in self.TARGET_TITLES)

    async def _extract_contact_info(self, row) -> Optional[Dict]:
        """Extract contact information from a row"""
        try:
            # Get basic info
            name = await row.query_selector(".contact-name")
            title = await row.query_selector(".job-title")
            
            if not name or not title:
                return None
                
            # Click reveal email
            reveal_button = await row.query_selector('button:has-text("Access email")')
            if reveal_button:
                await self._wait_for_rate_limit("reveal")
                await reveal_button.click()
                await self._wait_with_random_delay(0.5, 1)
                
                # Get revealed email
                email_element = await row.query_selector(".revealed-email")
                email = await email_element.inner_text() if email_element else None
                
                return {
                    "name": await name.inner_text(),
                    "title": await title.inner_text(),
                    "email": email
                }
                
        except Exception as e:
            logger.error(f"Failed to extract contact: {str(e)}")
            
        return None

    async def _verify_login(self) -> bool:
        """Verify successful login"""
        try:
            # Wait for dashboard element
            await self.page.wait_for_selector(".dashboard-container", timeout=5000)
            return True
        except PlaywrightTimeout:
            return False

    async def _wait_for_rate_limit(self, action_type: str):
        """Handle rate limiting for different action types"""
        now = datetime.now()
        
        if action_type == "search":
            time_since_last = now - self.last_search
            if time_since_last < self.search_delay:
                await asyncio.sleep(
                    (self.search_delay - time_since_last).total_seconds()
                )
            self.last_search = datetime.now()
            
        elif action_type == "reveal":
            time_since_last = now - self.last_reveal
            if time_since_last < self.reveal_delay:
                await asyncio.sleep(
                    (self.reveal_delay - time_since_last).total_seconds()
                )
            self.last_reveal = datetime.now()

    async def _wait_with_random_delay(self, min_seconds: float, max_seconds: float):
        """Add random delay between actions"""
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)

    async def _type_with_random_delays(
        self,
        selector: str,
        text: str,
        delay_range: Tuple[float, float] = (0.1, 0.3)
    ):
        """Type text with random delays between characters"""
        element = await self.page.wait_for_selector(selector)
        for char in text:
            await element.type(char)
            await asyncio.sleep(random.uniform(*delay_range))

    def get_metrics(self) -> Dict:
        """Get agent metrics"""
        return {
            "total_searches": len(self.current_results),
            "extracted_contacts": len(self.extracted_contacts),
            "error_count": self.error_count,
            "last_search": self.last_search.isoformat() if self.last_search else None,
            "last_reveal": self.last_reveal.isoformat() if self.last_reveal else None
        }
"""
Enhanced autonomous agent for RocketReach interactions with vision-based navigation
"""
from typing import List, Dict, Optional, Tuple
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import Page
from src.services.vision_service import VisionService
from src.services.action_parser import ActionParser
from src.services.navigation_state import NavigationState, NavigationStateMachine
from src.services.validation_service import ValidationService, ValidationResult
from src.services.screenshot_pipeline import ScreenshotPipeline
from src.services.result_collector import ResultCollector, SearchResult
from src.utils.exceptions import AutomationError, ValidationError

logger = logging.getLogger(__name__)

class RocketReachAgent:
    """Vision-based autonomous agent for RocketReach interactions"""
    
    # Target job titles that indicate relevant contacts
    TARGET_TITLES = {
        "Chief Executive Officer",
        "CEO",
        "President",
        "Chief Financial Officer", 
        "CFO",
        "Director of Finance",
        "Director of FP&A",
    }
    
    # Navigation prompts for specific UI elements
    NAVIGATION_PROMPTS = {
        'companies_tab': """
            Find the "Companies" tab in the navigation.
            Look for:
            1. Tab next to People tab
            2. The text "Companies"
            3. Located in main navigation area
            Click this element precisely.
        """,
        'search_box': """
            Locate the company search input field.
            Look for:
            1. A prominent search bar
            2. Placeholder about company name/domain
            3. Located at top of page
            Use the most reliable selector.
        """,
        'search_employees': """
            Find the "Search Employees" button.
            Look for:
            1. Blue button with "Search Employees" text
            2. Located in company search results
            3. Next to company information
            Click the correct button for the matching domain.
        """
    }
    
    def __init__(
        self,
        page: Page,
        vision_service: VisionService,
        action_parser: ActionParser,
        state_machine: NavigationStateMachine,
        validation_service: ValidationService,
        screenshot_pipeline: ScreenshotPipeline,
        result_collector: ResultCollector,
    ):
        self.page = page
        self.vision_service = vision_service
        self.action_parser = action_parser
        self.state_machine = state_machine
        self.validation_service = validation_service
        self.screenshot_pipeline = screenshot_pipeline
        self.result_collector = result_collector
        
        # State tracking
        self.current_state = {
            'company': None,
            'domain': None,
            'page_number': 1,
            'results_found': 0,
            'last_action': None,
            'error_count': 0,
            'rate_limit_hits': 0
        }
        
        # Configurable limits
        self.max_retries = 3
        self.max_pages = 10
        self.max_results = 5
        self.action_delay = 0.5
        self.page_delay = 1.0
        
        # Rate limiting
        self.last_action_time = datetime.min
        self.page_load_timeout = 10000
        self.element_timeout = 5000

    async def login(self, email: str, password: str) -> bool:
        """Login to RocketReach with vision-based validation"""
        try:
            await self.state_machine.transition('init_login')
            await self.page.goto("https://rocketreach.co/")
            
            # Click login button
            login_screenshot = await self.screenshot_pipeline.capture_optimized()
            login_result = await self.vision_service.analyze_screenshot(
                login_screenshot,
                "Find and click the login button in the top navigation."
            )
            await self._execute_action(login_result['next_action'])
            
            # Fill credentials
            email_result = await self._type_with_validation(
                'input[type="email"]',
                email,
                "email input"
            )
            if not email_result.is_valid:
                raise ValidationError(f"Email input failed: {email_result.errors}")
                
            password_result = await self._type_with_validation(
                'input[type="password"]',
                password,
                "password input"
            )
            if not password_result.is_valid:
                raise ValidationError(f"Password input failed: {password_result.errors}")
            
            # Click login
            login_button = await self.page.wait_for_selector(
                'button:has-text("Log In")',
                timeout=self.element_timeout
            )
            await login_button.click()
            
            # Verify login success
            await self.page.wait_for_selector(
                '[data-testid="user-menu"]',
                timeout=self.page_load_timeout
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            await self._handle_error(e)
            return False

    def get_metrics(self) -> Dict:
        """Get agent metrics"""
        return {
            'state': self.current_state,
            'total_results': self.current_state['results_found'],
            'error_rate': self.current_state['error_count'] / max(self.current_state['results_found'], 1),
            'rate_limit_hits': self.current_state['rate_limit_hits'],
            'pages_processed': self.current_state['page_number']
        }

    async def search_company(self, domain: str) -> List[Dict]:
        """Search company by domain with enhanced zoom handling"""
        try:
            self.current_state['domain'] = domain
            await self.state_machine.transition('init_search')
            
            # Navigate to companies tab
            await self._navigate_to_companies()
            
            # Search company domain
            search_result = await self._search_domain(domain)
            if not search_result:
                logger.warning(f"Company not found for domain: {domain}")
                return []
            
            # Click Search Employees for main result
            await self._click_search_employees()
            
            # Set zoom to 50% - New required step
            await self._set_zoom_level(50)
            
            # Extract contacts across pages
            contacts = await self._extract_all_contacts()
            
            # Store results
            for contact in contacts:
                result = SearchResult(
                    company_name=contact["company"],
                    person_name=contact["name"],
                    title=contact["title"],
                    email=contact.get("email"),
                    confidence=contact.get("confidence", 0.8),
                    source="rocketreach"
                )
                await self.result_collector.add_result(result)
            
            return contacts
            
        except Exception as e:
            logger.error(f"Company search failed: {str(e)}")
            await self._handle_error(e)
            return []
        
    async def _set_zoom_level(self, zoom_level: int):
        """Set page zoom level"""
        try:
            await self.page.evaluate(
                f'document.body.style.zoom = "{zoom_level}%"'
            )
            # Wait for zoom to take effect
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Failed to set zoom level: {str(e)}")

    async def _navigate_to_companies(self):
        """Navigate to companies search with vision guidance"""
        companies_screenshot = await self.screenshot_pipeline.capture_optimized()
        companies_result = await self.vision_service.analyze_screenshot(
            companies_screenshot,
            self.NAVIGATION_PROMPTS['companies_tab']
        )
        await self._execute_action(companies_result['next_action'])

    async def _search_domain(self, domain: str) -> bool:
        """Search company by domain with validation"""
        try:
            # Find and fill search input
            search_screenshot = await self.screenshot_pipeline.capture_optimized()
            search_result = await self.vision_service.analyze_screenshot(
                search_screenshot,
                self.NAVIGATION_PROMPTS['search_box']
            )
            
            search_input = await self.page.wait_for_selector(
                'input[placeholder*="company"]',
                timeout=self.element_timeout
            )
            await search_input.fill(domain)
            await search_input.press("Enter")
            
            # Wait for and validate results
            await self.page.wait_for_selector(
                '.company-results',
                timeout=self.page_load_timeout
            )
            
            # Check if company found
            company_count = await self.page.locator('.company-result').count()
            return company_count > 0
            
        except Exception as e:
            logger.error(f"Domain search failed: {str(e)}")
            return False

    async def _click_search_employees(self):
        """Click Search Employees with enhanced vision guidance"""
        try:
            # Take screenshot focused on search area
            button_screenshot = await self.screenshot_pipeline.capture_optimized()
            button_result = await self.vision_service.analyze_screenshot(
                button_screenshot,
                self.NAVIGATION_PROMPTS['search_employees']
            )
            
            # Execute with validation
            action_result = await self._execute_action(button_result['next_action'])
            if not action_result:
                raise AutomationError("Failed to click Search Employees")
            
            # Wait for navigation
            await self.page.wait_for_load_state("networkidle")
            
        except Exception as e:
            logger.error(f"Failed to click Search Employees: {str(e)}")
            raise


    async def _extract_all_contacts(self) -> List[Dict]:
        """Extract matching contacts across multiple pages"""
        contacts = []
        current_page = 1
        
        while (
            current_page <= self.max_pages and 
            len(contacts) < self.max_results
        ):
            try:
                # Wait for results to load
                await self.page.wait_for_load_state("networkidle")
                await asyncio.sleep(self.page_delay)
                
                # Extract contacts on current page
                page_contacts = await self._extract_page_contacts()
                contacts.extend(page_contacts)
                
                if len(contacts) >= self.max_results:
                    break
                    
                # Try next page
                if not await self._go_to_next_page(current_page):
                    break
                    
                current_page += 1
                self.current_state['page_number'] = current_page
                
            except Exception as e:
                logger.error(f"Page extraction failed: {str(e)}")
                break
        
        return contacts[:self.max_results]

    async def _extract_page_contacts(self) -> List[Dict]:
        """Extract contacts from current page with enhanced validation"""
        contacts = []
        try:
            rows = await self.page.query_selector_all(".contact-row")
            
            for row in rows:
                if len(contacts) >= self.max_results:
                    break
                    
                try:
                    title_element = await row.query_selector(".title")
                    if not title_element:
                        continue
                        
                    title = await title_element.inner_text()
                    if not self._is_target_title(title):
                        continue
                    
                    contact = await self._extract_contact_info(row)
                    if contact:
                        contacts.append(contact)
                        
                except Exception as e:
                    logger.error(f"Contact extraction failed: {str(e)}")
                    continue
            
            return contacts
            
        except Exception as e:
            logger.error(f"Page contacts extraction failed: {str(e)}")
            return []

    async def _extract_contact_info(self, row) -> Optional[Dict]:
        """Extract and validate contact information from a row"""
        try:
            # Get basic info
            name_element = await row.query_selector(".name")
            title_element = await row.query_selector(".title")
            company_element = await row.query_selector(".company")
            
            if not all([name_element, title_element, company_element]):
                return None
                
            name = await name_element.inner_text()
            title = await title_element.inner_text()
            company = await company_element.inner_text()
            
            # Click Get Contact Info
            info_button = await row.query_selector(
                'button:has-text("Get Contact Info")'
            )
            if not info_button:
                return None
                
            await info_button.click()
            await asyncio.sleep(self.action_delay)
            
            # Get revealed email
            email_element = await row.query_selector(".revealed-email")
            email = await email_element.inner_text() if email_element else None
            
            # Validate email
            if email:
                email_validation = await self.validation_service.validate_email(
                    email,
                    self.current_state['domain']
                )
                if not email_validation.is_valid:
                    email = None
            
            return {
                "name": name.strip(),
                "title": title.strip(),
                "company": company.strip(),
                "email": email.strip() if email else None,
                "confidence": 0.9 if email else 0.7
            }
            
        except Exception as e:
            logger.error(f"Contact info extraction failed: {str(e)}")
            return None

    def _is_target_title(self, title: str) -> bool:
        """Check if title matches target positions"""
        if not title:
            return False
            
        title = title.lower()
        return any(
            target.lower() in title or
            title in target.lower()
            for target in self.TARGET_TITLES
        )

    async def _go_to_next_page(self, current_page: int) -> bool:
        """Navigate to next page with vision guidance"""
        try:
            # Get pagination controls
            pagination_screenshot = await self.screenshot_pipeline.capture_optimized()
            pagination_result = await self.vision_service.analyze_screenshot(
                pagination_screenshot,
                self.NAVIGATION_PROMPTS['pagination']
            )
            
            # Try clicking next page number
            next_page = str(current_page + 1)
            next_button = await self.page.query_selector(
                f'[aria-label="Page {next_page}"]'
            )
            
            if not next_button:
                return False
                
            await next_button.click()
            await self.page.wait_for_load_state("networkidle")
            
            # Verify page changed
            new_page_element = await self.page.query_selector(
                f'[aria-current="page"]:has-text("{next_page}")'
            )
            return bool(new_page_element)
            
        except Exception as e:
            logger.error(f"Pagination failed: {str(e)}")
            return False

    async def _type_with_validation(
        self,
        selector: str,
        text: str,
        field_name: str = "input field"
    ) -> ValidationResult:
        """Type text with validation and retry"""
        try:
            element = await self.page.wait_for_selector(
                selector,
                timeout=self.element_timeout
            )
            if not element:
                return ValidationResult(
                    is_valid=False,
                    confidence=0.0,
                    errors=[f"{field_name} not found"]
                )
            
            # Clear existing text
            await element.click()
            await element.press("Control+A")
            await element.press("Backspace")
            
            # Type text with human-like delays
            for char in text:
                await element.type(char)
                await asyncio.sleep(0.05)
            
            # Validate input
            if "password" not in selector.lower():
                input_value = await element.input_value()
                if input_value != text:
                    return ValidationResult(
                        is_valid=False,
                        confidence=0.0,
                        errors=[f"Input validation failed for {field_name}"]
                    )
            
            return ValidationResult(
                is_valid=True,
                confidence=1.0,
                errors=[]
            )
            
        except Exception as e:
            logger.error(f"Typing failed: {str(e)}")
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                errors=[str(e)]
            )

    async def _execute_action(self, action: Dict) -> bool:
        """Execute parsed action with validation and retry logic"""
        try:
            validation_result = await self.validation_service.validate_action(action)
            if not validation_result.is_valid:
                logger.error(f"Invalid action: {validation_result.errors}")
                return False
            
            # Wait for rate limiting
            await asyncio.sleep(self.action_delay)
            
            # Execute based on type
            if action["type"] == "click":
                if "selector" in action["target"]:
                    element = await self.page.wait_for_selector(
                        action["target"]["selector"],
                        timeout=self.element_timeout
                    )
                    if not element:
                        return False
                    await element.click()
                else:
                    await self.page.mouse.click(
                        action["target"]["x"],
                        action["target"]["y"]
                    )
            
            elif action["type"] == "type":
                result = await self._type_with_validation(
                    action["target"]["selector"],
                    action["value"]
                )
                return result.is_valid
            
            elif action["type"] == "wait":
                await asyncio.sleep(float(action["duration"]))
            
            elif action["type"] == "scroll":
                await self.page.evaluate(
                    'window.scrollBy(0, arguments[0])',
                    action["amount"]
                )
                
            return True
            
        except Exception as e:
            logger.error(f"Action execution failed: {str(e)}")
            return False

    async def _handle_error(self, error: Exception):
        """Enhanced error handling with recovery logic"""
        self.current_state['error_count'] += 1
        self.current_state['last_action'] = 'error'
        
        if "rate limit" in str(error).lower():
            self.current_state['rate_limit_hits'] += 1
            await asyncio.sleep(60)
        
        if "timeout" in str(error).lower():
            await self.page.reload()
            await asyncio.sleep(self.action_delay)
        
        if self.current_state['error_count'] >= self.max_retries:
            raise AutomationError(
                f"Too many errors ({self.current_state['error_count']}): {str(error)}"
            )

    async def cleanup(self):
        """Cleanup resources and reset state"""
        try:
            # Reset zoom
            await self.page.evaluate('document.body.style.zoom = "100%"')
            
            # Clear state
            self.current_state = {
                'company': None,
                'domain': None,
                'page_number': 1,
                'results_found': 0,
                'last_action': None,
                'error_count': 0,
                'rate_limit_hits': 0
            }
            
            # Clear any modals or popups
            try:
                modal_close = await self.page.wait_for_selector(
                    '[aria-label="Close"]',
                    timeout=2000
                )
                if modal_close:
                    await modal_close.click()
            except Exception:
                pass
            
            await self.state_machine.cleanup()
            
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")

"""
Enhanced autonomous agent for Apollo.io interactions with robust error handling and state management
"""
from typing import List, Dict, Optional, Tuple
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
import re

from playwright.async_api import Page
from src.services.vision_service import VisionService
from src.services.action_parser import ActionParser
from src.services.navigation_state import NavigationState, NavigationStateMachine
from src.services.validation_service import ValidationService, ValidationResult
from src.services.screenshot_pipeline import ScreenshotPipeline
from src.services.result_collector import ResultCollector, SearchResult
from src.utils.exceptions import AutomationError, ValidationError

logger = logging.getLogger(__name__)

class ApolloAutonomousAgent:
    """Vision-based autonomous agent for Apollo.io interactions"""
    
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
        'people_tab': """
            Locate the "People" tab in the left sidebar navigation.
            Look for:
            1. A sidebar menu on the left side
            2. An icon with people/user symbol
            3. The text "People" next to the icon
            Identify the most reliable way to click this element.
        """,
        'company_tab': """
            Find the "Company" tab/filter option.
            Look for:
            1. Filter or tab sections
            2. Text saying "Company" or company icon
            3. Any dropdown or expandable company filter
            Determine the most precise selector or click coordinates.
        """,
        'search_box': """
            Locate the main search input field.
            Look for:
            1. A prominent search box
            2. Placeholder text about searching
            3. Search icon or magnifying glass
            Find the most reliable input selector.
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
        # Initialize state first
        self.current_state = {
            'company': None,
            'page': None,
            'last_action': None,
            'error_count': 0,
            'rate_limit_hits': 0,
            'results_found': 0
        }
        
        # Service assignments
        self.page = page
        self.vision_service = vision_service
        self.action_parser = action_parser
        self.state_machine = state_machine
        self.validation_service = validation_service
        self.screenshot_pipeline = screenshot_pipeline
        self.result_collector = result_collector
        
        # Configurable limits
        self.max_results = 5
        self.max_errors = 3
        self.max_retries = 3
        self.action_delay = timedelta(milliseconds=500)
        self.search_delay = timedelta(seconds=2)
        self.rate_limit_delay = timedelta(seconds=60)
        
        # Rate limiting
        self.last_action_time = datetime.min
        self.rate_limit_reset = datetime.min

    async def login(self, email: str, password: str) -> bool:
        """Enhanced login flow with navigation and state management"""
        try:
            # Initialize navigation context
            await self.state_machine.initialize_search('apollo', 'login')
            self.state['page'] = 'login'
            
            # Navigate to login page
            try:
                await self.page.goto("https://app.apollo.io/#/login", 
                                wait_until='networkidle',
                                timeout=30000)
                await self.page.wait_for_load_state('domcontentloaded')
            except Exception as e:
                raise AutomationError(f"Navigation failed: {str(e)}")

            # Wait for Apollo.io logo to confirm page load
            await self.page.wait_for_selector('img[alt="Apollo.io"]')
            
            # Wait for email field using Work Email placeholder
            email_input = await self.page.wait_for_selector('input[placeholder="Work Email"]', timeout=10000)
            if not email_input:
                raise AutomationError("Email input not found")
            await email_input.fill(email)
            
            # Wait for password field using the correct placeholder
            password_input = await self.page.wait_for_selector('input[placeholder="Enter your password"]', timeout=10000)
            if not password_input:
                raise AutomationError("Password input not found")
            await password_input.fill(password)
            
            # Click the Log In button using exact text
            login_button = await self.page.wait_for_selector('button:has-text("Log In")', timeout=10000)
            if not login_button:
                raise AutomationError("Login button not found")
            await login_button.click()
            
            # Wait for successful login redirection
            try:
                await self.page.wait_for_navigation(timeout=30000)
                await self.page.wait_for_load_state('networkidle')
            except Exception as e:
                raise AutomationError(f"Navigation after login failed: {str(e)}")
            
            # Verify login success
            success = await self._verify_login_success()
            if not success:
                raise AutomationError("Login verification failed")
                
            self.state['page'] = 'home'
            return True
                
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            await self._handle_error(e)
            raise AutomationError(f"Failed to login: {str(e)}")

    async def _verify_login_success(self) -> bool:
        """Enhanced login verification"""
        try:
            await asyncio.sleep(2)  # Wait for redirect
            
            # Check URL
            current_url = self.page.url
            if not current_url.startswith("https://app.apollo.io/"):
                return False
            
            # Try multiple selectors that indicate successful login
            success_selectors = [
                '[data-testid="user-menu"]',  # Primary selector
                '.user-profile',              # Backup selector
                'button:has-text("Power-ups")',  # Another indicator of logged-in state
                '.apollo-nav-menu'            # Main navigation menu
            ]
            
            for selector in success_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=5000)
                    if element:
                        return True
                except Exception:
                    continue
                    
            return False
                
        except Exception as e:
            logger.error(f"Login verification failed: {str(e)}")
            return False

    def _validate_state(self) -> bool:
        """Validate that state is properly initialized"""
        required_fields = {
            'company', 'page', 'last_action', 
            'error_count', 'rate_limit_hits', 'results_found'
        }
        return all(field in self.current_state for field in required_fields)

    @property
    def state(self) -> dict:
        """Safe state access with validation"""
        if not hasattr(self, 'current_state'):
            self.current_state = {
                'company': None,
                'page': None,
                'last_action': None,
                'error_count': 0,
                'rate_limit_hits': 0,
                'results_found': 0
            }
        return self.current_state
    
    async def search_company(self, company_name: str) -> List[Dict]:
        """Enhanced company search with improved navigation and validation"""
        try:
            self.current_state['company'] = company_name
            await self.state_machine.transition('init_search')
            
            # Navigate to search interface
            await self._navigate_to_search()
            await self._wait_for_rate_limit()
            
            # Enter company search
            search_input = await self.page.wait_for_selector(
                'input[type="text"]',
                timeout=5000
            )
            if not search_input:
                raise AutomationError("Search input not found")
            
            await self._type_with_validation(
                'input[type="text"]',
                company_name,
                "company search"
            )
            
            # Wait for and select company
            await self._select_company_from_dropdown(company_name)
            
            # Apply job title sort
            await self._sort_results()
            
            # Extract matching contacts
            contacts = await self._extract_matching_contacts()
            if not contacts:
                logger.warning(f"No matching contacts found for {company_name}")
            
            # Store results
            for contact in contacts:
                result = SearchResult(
                    company_name=company_name,
                    person_name=contact["name"],
                    title=contact["title"],
                    email=contact.get("email"),
                    confidence=contact.get("confidence", 0.8),
                    source="apollo"
                )
                await self.result_collector.add_result(result)
            
            return contacts
            
        except Exception as e:
            logger.error(f"Company search failed: {str(e)}")
            await self._handle_error(e)
            raise

    async def _navigate_to_search(self):
        """Enhanced navigation with specific vision prompts"""
        try:
            # Click People tab
            people_screenshot = await self.screenshot_pipeline.capture_optimized()
            people_result = await self.vision_service.analyze_screenshot(
                people_screenshot,
                self.NAVIGATION_PROMPTS['people_tab']
            )
            await self._execute_action(people_result['next_action'])
            await self._wait_for_rate_limit()
            
            # Click Company tab
            company_screenshot = await self.screenshot_pipeline.capture_optimized()
            company_result = await self.vision_service.analyze_screenshot(
                company_screenshot,
                self.NAVIGATION_PROMPTS['company_tab']
            )
            await self._execute_action(company_result['next_action'])
            
        except Exception as e:
            logger.error(f"Navigation failed: {str(e)}")
            raise AutomationError(f"Failed to navigate to search: {str(e)}")

    async def _type_with_validation(
        self,
        selector: str,
        text: str,
        field_name: str = "input field",
        retry_count: int = 0
    ) -> ValidationResult:
        """Enhanced typing with validation and retry logic"""
        try:
            element = await self.page.wait_for_selector(selector, timeout=5000)
            if not element:
                raise ValidationError(f"{field_name} element not found")
            
            # Clear existing text
            await element.click()
            await element.press("Control+A")
            await element.press("Backspace")
            
            # Type with human-like delays
            for char in text:
                await element.type(char)
                await asyncio.sleep(0.05)  # Reduced delay for tests
            
            # Validate input
            input_value = await element.input_value()
            # Skip exact validation for password fields
            if "password" in selector.lower():
                return ValidationResult(
                    is_valid=True,
                    confidence=1.0,
                    errors=[]
                )
                
            if input_value != text:
                if retry_count < self.max_retries:
                    await asyncio.sleep(0.5)
                    return await self._type_with_validation(
                        selector,
                        text,
                        field_name,
                        retry_count + 1
                    )
                raise ValidationError(f"Input validation failed for {field_name}")
            
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

    async def _select_company_from_dropdown(self, company_name: str):
        """Enhanced company selection with retry logic"""
        try:
            await self.page.wait_for_selector(".company-dropdown-item", timeout=5000)
            
            dropdown_screenshot = await self.screenshot_pipeline.capture_optimized()
            vision_result = await self.vision_service.analyze_with_context(
                dropdown_screenshot,
                {
                    "type": "company_selection",
                    "company": company_name,
                    "expected_elements": ["dropdown", "company name", "domain"]
                }
            )
            
            action, fallbacks = await self.action_parser.parse_action(vision_result)
            success = await self._execute_action(action)
            
            if not success and fallbacks:
                for fallback in fallbacks:
                    if await self._execute_action(fallback):
                        return
                        
            if not success:
                raise AutomationError("Failed to select company")
            
        except Exception as e:
            logger.error(f"Company selection failed: {str(e)}")
            raise AutomationError(f"Failed to select company: {str(e)}")

    async def _sort_results(self):
        """Enhanced results sorting with validation"""
        try:
            # Click job title header
            title_header = await self.page.wait_for_selector(
                'th:has-text("Job Title")',
                timeout=5000
            )
            if not title_header:
                raise AutomationError("Job title header not found")
            
            await title_header.click()
            
            # Click sort ascending if needed
            sort_menu = await self.page.wait_for_selector(
                '.sort-menu',
                timeout=5000
            )
            if sort_menu:
                asc_option = await sort_menu.wait_for_selector(
                    'text=Sort ascending',
                    timeout=2000
                )
                if asc_option:
                    await asc_option.click()
            
            # Wait for sort to complete
            await self.page.wait_for_load_state("networkidle")
            
        except Exception as e:
            logger.error(f"Sort failed: {str(e)}")
            raise AutomationError(f"Failed to sort results: {str(e)}")

    async def _extract_matching_contacts(self) -> List[Dict]:
        """Extract matching contacts with result limit"""
        contacts = []
        current_page = 1
        
        while (
            current_page <= 10 and  # Keep existing page limit
            len(contacts) < self.max_results  # New result limit
        ):
            try:
                # Wait for results to load
                await self.page.wait_for_load_state("networkidle")
                
                # Get all contact rows
                rows = await self.page.query_selector_all("tr")
                
                for row in rows:
                    # Break if we hit the result limit
                    if len(contacts) >= self.max_results:
                        break
                        
                    try:
                        # Get title first to filter quickly
                        title_element = await row.query_selector("td:nth-child(2)")
                        if not title_element:
                            continue
                            
                        title = await title_element.inner_text()
                        if not self._is_target_title(title):
                            continue
                        
                        # Now extract other fields
                        name_element = await row.query_selector("td:nth-child(1)")
                        if not name_element:
                            continue
                        
                        name = await name_element.inner_text()
                        
                        # Updated email button selector
                        email_button = await row.query_selector(
                            'button:has-text("Access email")'
                        )
                        if not email_button:
                            continue
                            
                        # Click and wait for email reveal
                        await email_button.click()
                        await asyncio.sleep(0.5)  # Wait for reveal animation
                        
                        # Updated revealed email selector
                        email_element = await row.query_selector(".revealed-email")
                        email = await email_element.inner_text() if email_element else None
                        
                        if name and title and email:
                            contacts.append({
                                "name": name.strip(),
                                "title": title.strip(),
                                "email": email.strip(),
                                "confidence": 0.9
                            })
                            self.current_state['results_found'] += 1
                        
                    except Exception as row_error:
                        logger.error(f"Row processing error: {str(row_error)}")
                        continue
                
                # Check limits before pagination
                if len(contacts) >= self.max_results:
                    break
                    
                # Try next page
                if not await self._go_to_next_page(current_page):
                    break
                    
                current_page += 1
                self.current_state['page_number'] = current_page
                
            except Exception as page_error:
                logger.error(f"Page processing error: {str(page_error)}")
                break
        
        return contacts[:self.max_results]  # Ensure we don't exceed limit

    async def _extract_contact_info(self, row) -> Optional[Dict]:
        """Extract and validate contact information from a row"""
        try:
            # Get name
            name_element = await row.query_selector("td:nth-child(1)")
            if not name_element:
                return None
            name = await name_element.inner_text()
            
            # Get title
            title_element = await row.query_selector("td:nth-child(2)")
            if not title_element:
                return None
            title = await title_element.inner_text()
            
            # Basic validation
            if not name or not title:
                return None
                
            # Get email button
            email_button = await row.query_selector("button:has-text('Access email')")
            if not email_button:
                return None
            
            # Click and get email
            await email_button.click()
            await asyncio.sleep(0.5)  # Wait for reveal
            
            email_element = await row.query_selector(".revealed-email")
            email = await email_element.inner_text() if email_element else None
            
            # Validate email
            if email:
                email_validation = await self.validation_service.validate_email(
                    email,
                    self.current_state['company']
                )
                if not email_validation.is_valid:
                    email = None
            
            return {
                "name": name.strip(),
                "title": title.strip(),
                "email": email,
                "confidence": 0.9 if email else 0.7
            }
            
        except Exception as e:
            logger.error(f"Contact info extraction failed: {str(e)}")
            return None

    def _is_target_title(self, title: str) -> bool:
        """Enhanced title matching with fuzzy matching"""
        if not title:
            return False
            
        title = title.lower()
        return any(
            target.lower() in title or
            title in target.lower()
            for target in self.TARGET_TITLES
        )

    async def _go_to_next_page(self, current_page: int) -> bool:
        """Enhanced pagination with better error handling"""
        try:
            next_button = await self.page.query_selector('[aria-label="Next"]')
            if not next_button:
                return False
                
            is_disabled = await next_button.get_attribute('disabled')
            if is_disabled:
                return False
                
            await next_button.click()
            
            # Wait for page transition
            await self.page.wait_for_load_state("networkidle")
            
            # Verify page changed
            new_page_indicator = await self.page.query_selector(
                f'[aria-label="Page {current_page + 1}"]'
            )
            return bool(new_page_indicator)
            
        except Exception as e:
            logger.error(f"Pagination failed: {str(e)}")
            return False

    async def _wait_for_rate_limit(self):
        """Enhanced rate limiting with reset handling"""
        now = datetime.now()
        
        # Check if in rate limit cooldown
        if now < self.rate_limit_reset:
            await asyncio.sleep(
                (self.rate_limit_reset - now).total_seconds()
            )
            return
        
        # Normal action delay
        time_since_last = now - self.last_action_time
        if time_since_last < self.action_delay:
            await asyncio.sleep(
                (self.action_delay - time_since_last).total_seconds()
            )
        
        self.last_action_time = datetime.now()

    async def _execute_action(self, action: Dict) -> bool:
        """Enhanced action execution with validation and retries"""
        try:
            validation_result = await self.validation_service.validate_action(action)
            if not validation_result.is_valid:
                logger.error(f"Invalid action: {validation_result.errors}")
                return False
            
            await self._wait_for_rate_limit()
            
            if action["type"] == "click":
                if "selector" in action["target"]:
                    element = await self.page.wait_for_selector(
                        action["target"]["selector"],
                        timeout=5000
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
                    action["value"],
                    "input field"
                )
                return result.is_valid
                
            return True
            
        except Exception as e:
            logger.error(f"Action execution failed: {str(e)}")
            return False

    async def _verify_login_success(self) -> bool:
        """Enhanced login verification"""
        try:
            await asyncio.sleep(2)  # Wait for redirect
            
            # Check URL
            current_url = self.page.url
            if not current_url.startswith("https://app.apollo.io/"):
                return False
                
            # Check for logged-in elements
            try:
                profile_element = await self.page.wait_for_selector(
                    '[data-testid="user-menu"]',
                    timeout=5000
                )
                return bool(profile_element)
            except Exception:
                # Try alternative selectors if the first one fails
                selectors = [
                    '.user-profile',
                    '.user-avatar',
                    '.logged-in-indicator'
                ]
                for selector in selectors:
                    try:
                        element = await self.page.wait_for_selector(selector, timeout=2000)
                        if element:
                            return True
                    except Exception:
                        continue
                return False
            
        except Exception as e:
            logger.error(f"Login verification failed: {str(e)}")
            return False

    async def _handle_error(self, error: Exception):
        """Enhanced error handling with rate limit detection"""
        self.current_state['error_count'] += 1
        
        if "rate limit" in str(error).lower():
            self.current_state['rate_limit_hits'] += 1
            self.rate_limit_reset = datetime.now() + self.rate_limit_delay
            
        if self.current_state['error_count'] >= self.max_errors:
            raise AutomationError(f"Too many errors: {str(error)}")

    async def cleanup(self):
        """Enhanced cleanup with resource management"""
        try:
            if self.state_machine:
                await self.state_machine.cleanup()
                
            if self.result_collector:
                await self.result_collector.cleanup_cache()
                
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
                
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")

    def get_metrics(self) -> Dict:
        """Get comprehensive agent metrics"""
        return {
            'total_searches': len(self.result_collector.results) if self.result_collector else 0,
            'error_count': self.current_state['error_count'],
            'rate_limit_hits': self.current_state['rate_limit_hits'],
            'last_action': self.last_action_time.isoformat(),
            'current_company': self.current_state['company'],
            'current_page': self.current_state['page'],
            'navigation_metrics': self.state_machine.get_metrics() if self.state_machine else {},
            'vision_metrics': self.vision_service.get_state_analysis_metrics() if self.vision_service else {}
        }
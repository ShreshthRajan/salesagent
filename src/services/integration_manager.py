# src/services/integration_manager.py
from typing import Dict, Optional, List, Any
import logging
import asyncio
from playwright.async_api import Page
from datetime import datetime

from src.utils.exceptions import IntegrationError, ConfigurationError  # Updated import line

from src.services.vision_service import VisionService
from src.services.action_parser import ActionParser
from src.services.navigation_state import NavigationStateMachine, NavigationState
from src.services.validation_service import ValidationService
from src.services.screenshot_pipeline import ScreenshotPipeline
from src.services.element_handler import ElementHandler
from src.utils.exceptions import IntegrationError

logger = logging.getLogger(__name__)

class IntegrationManager:
    async def _handle_element_not_found(self, error: Exception) -> bool:
        """Handle element not found errors with retries"""
        if self.retry_count < self.max_retries:
            self.retry_count += 1
            await asyncio.sleep(self.recovery_delay)
            return True
        return False

    async def _handle_validation_error(self, error: Exception) -> bool:
        """Handle validation errors with potential recovery"""
        self.metrics['validation_failures'] += 1
        if self.recovery_mode:
            return False
        self.recovery_mode = True
        return await self._try_recovery()

    async def _handle_timeout_error(self, error: Exception) -> bool:
        """Handle timeout errors with backoff"""
        if self.retry_count < self.max_retries:
            self.retry_count += 1
            await asyncio.sleep(self.recovery_delay * self.retry_count)
            return True
        return False

    async def _try_recovery(self) -> bool:
        """Attempt recovery from error state"""
        try:
            # Implement recovery logic
            return True
        except Exception as e:
            logger.error(f"Recovery failed: {str(e)}")
            return False
    
    def __init__(
        self,
        page: Optional[Page] = None,
        vision_service: Optional[VisionService] = None,
        action_parser: Optional[ActionParser] = None,
        state_machine: Optional[NavigationStateMachine] = None,
        validation_service: Optional[ValidationService] = None,
        screenshot_pipeline: Optional[ScreenshotPipeline] = None,
        element_handler: Optional[ElementHandler] = None
    ):
        self.page = page
        self.vision_service = vision_service
        self.action_parser = action_parser
        self.state_machine = state_machine
        self.validation_service = validation_service
        self.screenshot_pipeline = screenshot_pipeline
        self.element_handler = element_handler
        
        # Initialize metrics and state
        self.metrics = {
            'successful_actions': 0,
            'failed_actions': 0,
            'validation_failures': 0,
            'recovery_attempts': 0
        }
        self.retry_count = 0
        self.max_retries = 3
        self.recovery_delay = 1.0
        self.recovery_mode = False

    async def _setup_browser_listeners(self):
        """Setup browser event listeners"""
        await self.page.on("load", self._handle_page_load)
        await self.page.on("dialog", self._handle_dialog)
        await self.page.on("response", self._handle_response)

    def _initialize_metrics(self):
        """Initialize metrics tracking"""
        self.metrics = {
            'successful_actions': 0,
            'failed_actions': 0,
            'validation_failures': 0,
            'recovery_attempts': 0,
            'total_requests': 0,
            'average_response_time': 0,
            'error_count': 0
        }

    async def _handle_page_load(self):
        """Handle page load events"""
        await self._update_context("page_loaded", True)
        await self._trigger_state_update()

    async def _handle_dialog(self, dialog):
        """Handle browser dialogs"""
        await dialog.dismiss()
        await self._update_context("dialog_detected", True)

    async def _handle_response(self, response):
        """Handle network responses"""
        if response.status == 403:
            await self._handle_blocked_request()

    async def execute_vision_action(self) -> bool:
        """Execute vision-guided action with real-time validation"""
        try:
            # Capture current state
            screenshot = await self.screenshot_pipeline.capture_optimized(
                name=f"state_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                optimize=True
            )

            # Get vision analysis
            vision_result = await self.vision_service.analyze_screenshot(
                screenshot,
                custom_prompt=None
            )

            # Parse and validate action
            action, fallbacks = await self.action_parser.parse_action(vision_result)
            validation_result = await self.validation_service.validate_action(action)

            if not validation_result.is_valid:
                logger.warning(f"Invalid action detected: {validation_result.errors}")
                return await self._try_fallback_actions(fallbacks)

            # Execute action with element handler
            success = await self._execute_action(action)
            if success:
                self.metrics['successful_actions'] += 1
            else:
                self.metrics['failed_actions'] += 1

            return success

        except Exception as e:
            logger.error(f"Vision action execution failed: {str(e)}")
            self.metrics['failed_actions'] += 1
            return False

    async def _generate_dynamic_prompt(self) -> str:
        """Generate context-aware prompt based on current state"""
        current_state = self.state_machine.context.current_state
        previous_action = self.action_parser.last_action
        
        base_prompt = self.vision_service.templates['default']
        
        state_prompts = {
            NavigationState.SEARCHING: "Focus on identifying search results and person information.",
            NavigationState.PERSON_FOUND: "Look for email-related buttons or information.",
            NavigationState.ERROR: "Identify alternative paths or retry options."
        }
        
        additional_context = state_prompts.get(current_state, "")
        return f"{base_prompt}\n\nContext: {additional_context}"

    async def _execute_action(self, action: Dict) -> bool:
        """Execute action using element handler with real-time validation"""
        try:
            action_type = action['type']
            if action_type == 'click':
                if 'coordinates' in action['target']:
                    await self.page.mouse.click(
                        action['target']['coordinates']['x'],
                        action['target']['coordinates']['y']
                    )
                else:
                    await self.element_handler.click(action['target']['selector'])
            
            elif action_type == 'type':
                await self.element_handler.type_text(
                    action['target']['selector'],
                    action['value']
                )
                
            elif action_type == 'wait':
                await asyncio.sleep(float(action['duration']))
                
            return True
            
        except Exception as e:
            logger.error(f"Action execution failed: {str(e)}")
            return False

    async def _try_fallback_actions(self, fallbacks: List[Dict]) -> bool:
        """Try fallback actions in sequence"""
        for fallback in fallbacks:
            try:
                success = await self._execute_action(fallback)
                if success:
                    return True
            except Exception as e:
                logger.error(f"Fallback action failed: {str(e)}")
                continue
        return False

    async def _update_context(self, key: str, value: Any):
        """Update context with new information"""
        self.context[key] = value
        self.context['last_updated'] = datetime.now()

    async def _trigger_state_update(self):
        """Trigger state machine update based on new context"""
        current_state = self.state_machine.context.current_state
        
        if self.context.get('page_loaded'):
            await self.state_machine.transition({'type': 'page_load'})
            
        if self.context.get('dialog_detected'):
            await self.state_machine.transition({'type': 'interruption'})

    async def _handle_blocked_request(self):
        """Handle blocked requests with recovery"""
        await self.state_machine.transition({'type': 'error', 'reason': 'blocked'})
        await self._update_context("blocked_request", True)

    async def _handle_execution_error(self, error: Exception):
        """Handle execution errors with recovery"""
        await self.state_machine.transition({
            'type': 'error',
            'reason': str(error),
            'recoverable': isinstance(error, IntegrationError)
        })

    async def _update_navigation_state(self, action_success: bool):
        """Update navigation state based on action result"""
        await self.state_machine.transition({
            'success': action_success,
            'context': self.context,
            'timestamp': datetime.now().isoformat()
        })
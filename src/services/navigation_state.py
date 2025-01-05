# src/services/navigation_state.py
from enum import Enum
from typing import Optional, Dict, List, Any
import logging
from dataclasses import dataclass, field
import json
import aiofiles
from datetime import datetime
import asyncio
from src.utils.exceptions import NavigationError
from pathlib import Path 

logger = logging.getLogger(__name__)

class NavigationState(Enum):
    INITIAL = "initial"
    SEARCHING = "searching"
    PERSON_FOUND = "person_found"
    EMAIL_FOUND = "email_found"
    VALIDATING = "validating"
    RETRYING = "retrying"
    ERROR = "error"
    COMPLETE = "complete"

@dataclass
class NavigationContext:
    current_state: NavigationState
    target_company: str
    target_role: str
    found_person: Optional[str] = None
    found_email: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    start_time: datetime = field(default_factory=datetime.now)
    timeout_seconds: int = 300
    confidence_score: float = 0.0
    action_history: List[Dict] = field(default_factory=list)
    parallel_tasks: Dict[str, asyncio.Task] = field(default_factory=dict)

class NavigationStateMachine:
    """Manages navigation state transitions and parallel tasks"""
    
    def __init__(self):
        self.context = None
        self.state_history = []
        self.persistence_path = Path("data/navigation_state.json")
        self.timeout_monitor = None
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.state_transitions = {
            NavigationState.INITIAL: self._handle_initial,
            NavigationState.SEARCHING: self._handle_searching,
            NavigationState.PERSON_FOUND: self._handle_person_found,
            NavigationState.EMAIL_FOUND: self._handle_email_found,
            NavigationState.VALIDATING: self._handle_validating,
            NavigationState.RETRYING: self._handle_retrying,
            NavigationState.ERROR: self._handle_error,
            NavigationState.COMPLETE: self._handle_complete
        }

    async def cleanup(self):
        """Cleanup any running tasks"""
        if self.timeout_monitor:
            self.timeout_monitor.cancel()
            try:
                await self.timeout_monitor
            except asyncio.CancelledError:
                pass
            
        if self.context and self.context.parallel_tasks:
            for task in self.context.parallel_tasks.values():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def initialize_search(self, company: str, role: str) -> NavigationContext:
        """Initialize new search with monitoring"""
        if hasattr(self, 'cleanup'):
            await self.cleanup()
            self.context = NavigationContext(
                current_state=NavigationState.INITIAL,
                target_company=company,
                target_role=role
            )
            
            # Start timeout monitor
            self.timeout_monitor = asyncio.create_task(self._monitor_timeout())
            
            # Initialize parallel validation
            self.context.parallel_tasks['validation'] = asyncio.create_task(
                self._continuous_validation()
            )
            
            await self._save_state()
            return self.context

    async def transition(self, action_result: Dict) -> NavigationContext:
        """Handle state transition with parallel task management"""
        if not self.context:
            raise NavigationError("Navigation context not initialized")

        # Update state based on action result
        handler = self.state_transitions.get(self.context.current_state)
        if handler:
            await handler(action_result)
            
        await self._save_state()
        return self.context

    async def _handle_initial(self, action_result: Dict) -> None:
        """Handle initial state transitions"""
        if action_result.get('success'):
            self.context.current_state = NavigationState.SEARCHING
        else:
            self.context.current_state = NavigationState.ERROR

    async def _handle_searching(self, action_result: Dict) -> None:
        """Handle searching state transitions"""
        if action_result.get('person_found'):
            self.context.found_person = action_result['person_found']
            self.context.current_state = NavigationState.PERSON_FOUND
        elif self.context.attempts >= self.context.max_attempts:
            self.context.current_state = NavigationState.ERROR
        else:
            self.context.attempts += 1

    async def _handle_person_found(self, action_result: Dict) -> None:
        """Handle person found state transitions"""
        if action_result.get('email_found'):
            self.context.found_email = action_result['email_found']
            await self._handle_email_found(action_result)  # Use the updated handler
        elif self.context.attempts >= self.context.max_attempts:
            self.context.current_state = NavigationState.ERROR
        else:
            self.context.attempts += 1

    async def _handle_email_found(self, action_result: Dict) -> None:
        """Handle email found state transitions"""
        self.context.found_email = action_result.get('email_found')
        if action_result.get('validation_success') is False:
            self.context.current_state = NavigationState.RETRYING
        else:
            self.context.current_state = NavigationState.COMPLETE

    async def _handle_validating(self, action_result: Dict) -> None:
        """Handle validation state transitions"""
        if action_result.get('validation_success'):
            self.context.current_state = NavigationState.COMPLETE
        elif action_result.get('retry_needed'):
            self.context.current_state = NavigationState.RETRYING
        else:
            self.context.current_state = NavigationState.ERROR

    async def _handle_retrying(self, action_result: Dict) -> None:
        """Handle retry state transitions"""
        self.context.attempts = 0
        if action_result.get('reset'):
            self.context.current_state = NavigationState.INITIAL
        else:
            self.context.current_state = NavigationState.SEARCHING

    async def _handle_error(self, action_result: Dict) -> None:
        """Handle error state transitions"""
        if action_result.get('retry'):
            self.context.current_state = NavigationState.RETRYING
            self.context.attempts = 0

    async def _handle_complete(self, action_result: Dict) -> None:
        """Handle completion state"""
        pass

    async def _monitor_timeout(self):
        """Monitor for timeout condition"""
        while True:
            if self.context:
                elapsed = (datetime.now() - self.context.start_time).total_seconds()
                if elapsed > self.context.timeout_seconds:
                    await self.handle_timeout()
            await asyncio.sleep(1)

    async def handle_timeout(self):
        """Handle timeout condition"""
        logger.warning(f"Navigation timeout for {self.context.target_company}")
        self.context.current_state = NavigationState.ERROR
        await self._save_state()

    async def _continuous_validation(self):
        """Continuous validation task"""
        while True:
            if self.context and self.context.current_state not in [NavigationState.ERROR, NavigationState.COMPLETE]:
                await self._validate_current_state()
            await asyncio.sleep(5)

    async def _validate_current_state(self):
        """Validate current state and trigger recovery if needed"""
        if self.context.attempts >= self.context.max_attempts:
            await self._trigger_recovery()

    async def _trigger_recovery(self):
        """Trigger recovery process"""
        self.context.current_state = NavigationState.RETRYING
        self.context.attempts = 0
        logger.info(f"Triggered recovery for {self.context.target_company}")

    async def _save_state(self):
        """Save navigation state to disk"""
        if not self.context:
            return

        state_data = {
            'current_state': self.context.current_state.value,
            'target_company': self.context.target_company,
            'target_role': self.context.target_role,
            'found_person': self.context.found_person,
            'found_email': self.context.found_email,
            'attempts': self.context.attempts,
            'confidence_score': self.context.confidence_score,
            'action_history': self.context.action_history,
            'timestamp': datetime.now().isoformat()
        }

        async with aiofiles.open(self.persistence_path, 'w') as f:
            await f.write(json.dumps(state_data, indent=2))

    async def load_state(self) -> Optional[NavigationContext]:
        """Load navigation state from disk"""
        try:
            async with aiofiles.open(self.persistence_path, 'r') as f:
                state_data = json.loads(await f.read())
                
            self.context = NavigationContext(
                current_state=NavigationState[state_data['current_state']],
                target_company=state_data['target_company'],
                target_role=state_data['target_role'],
                found_person=state_data['found_person'],
                found_email=state_data['found_email'],
                attempts=state_data['attempts'],
                confidence_score=state_data['confidence_score']
            )
            self.context.action_history = state_data['action_history']
            
            return self.context
        except FileNotFoundError:
            return None
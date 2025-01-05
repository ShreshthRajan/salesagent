# tests/services/test_navigation_state.py
import pytest
from src.services.navigation_state import NavigationState

@pytest.fixture
def navigation_state():
    from src.services.navigation_state import NavigationStateMachine
    return NavigationStateMachine()

class TestNavigationState:
    @pytest.mark.asyncio
    async def test_state_transitions(self, navigation_state):
        context = await navigation_state.initialize_search("TestCo", "CEO")
        assert context.current_state.value == "initial"
        
        # Transition to searching
        await navigation_state.transition({"success": True})
        assert context.current_state.value == "searching"
        
        # Transition to person found
        await navigation_state.transition({"person_found": True})
        assert context.current_state.value == "person_found"
        
        # Transition to email found with failed validation
        await navigation_state.transition({
            "email_found": "test@example.com",
            "validation_success": False
        })
        assert context.current_state.value == "retrying"
# tests/services/test_navigation_state.py
from src.services.navigation_state import NavigationState

class TestNavigationState:
    async def test_error_recovery(self, navigation_state):
        context = await navigation_state.initialize_search("TestCo", "CEO")
        await navigation_state.transition({"success": False})
        assert context.current_state == NavigationState.ERROR
        await navigation_state.transition({"retry": True})
        assert context.current_state == NavigationState.RETRYING  # Update expected state
    
    async def test_state_transitions(self, navigation_state):
        context = await navigation_state.initialize_search("TestCo", "CEO")
        assert context.current_state.value == "initial"
        
        await navigation_state.transition({"success": True})
        assert context.current_state.value == "searching"
        assert context.current_state.value == "error"
        await navigation_state.transition({"retry": True})
        assert context.current_state.value == "initial"
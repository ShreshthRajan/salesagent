from typing import Dict, Optional, Tuple, List
import logging
from dataclasses import dataclass
from fuzzywuzzy import fuzz
from src.utils.exceptions import InvalidActionError

logger = logging.getLogger(__name__)

@dataclass
class ActionResult:
    success: bool
    error: Optional[str] = None
    retry_count: int = 0
    confidence: float = 0.0

class ActionParser:
    """Enhanced action parser with advanced features"""
    
    VALID_ACTIONS = {
        'click': {'required': ['target']},
        'type': {'required': ['target', 'value']},
        'wait': {'required': ['duration']},
        'scroll': {'required': ['direction']},
        'hover': {'required': ['target']},
        'drag': {'required': ['source', 'target']},
        'select': {'required': ['target', 'value']}
    }
    
    def __init__(self):
        self.action_history: List[Dict] = []
        self.fallback_strategies = {
            'click': self._get_click_fallbacks,
            'type': self._get_type_fallbacks,
            'select': self._get_select_fallbacks
        }
        self.confidence_threshold = 0.7

    def parse_action(self, vision_response: Dict) -> Tuple[Dict, List[Dict]]:
        """Parse vision response into executable action with fallbacks"""
        try:
            action = vision_response['next_action']
            
            if action['type'] not in self.VALID_ACTIONS:
                raise InvalidActionError(f"Invalid action type: {action['type']}")
            
            # Validate required fields
            required_fields = self.VALID_ACTIONS[action['type']]['required']
            if not all(field in action for field in required_fields):
                raise InvalidActionError(f"Missing required fields for {action['type']}")
            
            # Process coordinates or selector
            processed_action = self._process_action_target(action)
            
            # Generate fallback strategies
            fallbacks = self._generate_fallbacks(processed_action)
            
            # Add to history
            self.action_history.append(processed_action)
            
            return processed_action, fallbacks
            
        except KeyError as e:
            raise InvalidActionError(f"Missing required action field: {str(e)}")

    def _process_action_target(self, action: Dict) -> Dict:
        """Process action target into coordinates or selector"""
        processed = action.copy()
        
        if 'target' in action:
            if isinstance(action['target'], dict) and 'x' in action['target'] and 'y' in action['target']:
                # Already in coordinate format
                pass
            elif isinstance(action['target'], str):
                # Convert selector to preferred format
                processed['target'] = {
                    'selector': action['target'],
                    'fallback_selectors': self._generate_selector_variations(action['target'])
                }
        
        return processed

    def _generate_selector_variations(self, selector: str) -> List[str]:
        """Generate variations of a selector for fuzzy matching"""
        variations = []
        
        # Remove various attributes
        if '[' in selector:
            variations.append(selector.split('[')[0])
            
        # Handle compound selectors
        if ' > ' in selector:
            parts = selector.split(' > ')
            variations.extend([part for part in parts])
            
        # Add contains variations
        if '"' in selector:
            text = selector.split('"')[1]
            variations.append(f'*:contains("{text}")')
            
        return variations

    def _generate_fallbacks(self, action: Dict) -> List[Dict]:
        """Generate fallback strategies for the action"""
        strategy_generator = self.fallback_strategies.get(action['type'])
        if not strategy_generator:
            return []
            
        return strategy_generator(action)

    def _get_click_fallbacks(self, action: Dict) -> List[Dict]:
        """Generate fallback strategies for click actions"""
        fallbacks = []
        
        if 'selector' in action['target']:
            # Add coordinate-based fallback if available
            if 'coordinates' in action:
                fallbacks.append({
                    'type': 'click',
                    'target': {'x': action['coordinates']['x'], 'y': action['coordinates']['y']}
                })
            
            # Add fuzzy selector matches
            for selector in action['target']['fallback_selectors']:
                fallbacks.append({
                    'type': 'click',
                    'target': {'selector': selector}
                })
                
        return fallbacks

    def _get_type_fallbacks(self, action: Dict) -> List[Dict]:
        """Generate fallback strategies for type actions"""
        fallbacks = []
        
        if 'selector' in action['target']:
            # Try different input types
            input_types = ['input', 'textarea']
            for input_type in input_types:
                fallbacks.append({
                    'type': 'type',
                    'target': {'selector': f'{input_type}[type="text"]'},
                    'value': action['value']
                })
                
        return fallbacks

    def _get_select_fallbacks(self, action: Dict) -> List[Dict]:
        """Generate fallback strategies for select actions"""
        fallbacks = []
        
        if 'selector' in action['target']:
            # Try different selection methods
            fallbacks.append({
                'type': 'click',
                'target': action['target']
            })
            fallbacks.append({
                'type': 'type',
                'target': action['target'],
                'value': action['value']
            })
                
        return fallbacks
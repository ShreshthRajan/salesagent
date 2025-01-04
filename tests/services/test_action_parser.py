# tests/services/test_action_parser.py
class TestActionParser:
    def test_parse_valid_action(self, action_parser):
        vision_response = {
            "next_action": {
                "type": "click",
                "target": {
                    "selector": "#search-button",
                    "fallback_selectors": []  # Add this
                },
                "confidence": 0.95
            }
        }
        action, fallbacks = action_parser.parse_action(vision_response)
        assert action["type"] == "click"
        assert "target" in action

    def test_generate_fallbacks(self, action_parser):
        action = {
            "type": "click",
            "target": {
                "selector": "#search-button",
                "fallback_selectors": []
            }
        }
        fallbacks = action_parser._generate_fallbacks(action)
        assert isinstance(fallbacks, list)
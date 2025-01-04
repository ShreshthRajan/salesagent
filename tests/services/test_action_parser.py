class TestActionParser:
    def test_parse_valid_action(self, action_parser):
        vision_response = {
            "next_action": {
                "type": "click",
                "target": {"selector": "#search-button"},
                "confidence": 0.95
            }
        }
        action, fallbacks = action_parser.parse_action(vision_response)
        assert action["type"] == "click"
        assert "selector" in action["target"]

    def test_generate_fallbacks(self, action_parser):
        action = {
            "type": "click",
            "target": {"selector": "#search-button"}
        }
        fallbacks = action_parser._generate_fallbacks(action)
        assert len(fallbacks) > 0
        assert all(fb["type"] == "click" for fb in fallbacks)
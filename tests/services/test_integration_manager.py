from unittest.mock import patch, AsyncMock

class TestIntegrationManager:
    async def test_execute_vision_action(self, integration_manager, tmp_path):
        with patch("src.services.vision_service.VisionService.analyze_screenshot", 
                  AsyncMock(return_value={
                      "page_state": "search",
                      "next_action": {
                          "type": "click",
                          "target": {"selector": "#search-button"}
                      }
                  })):
            result = await integration_manager.execute_vision_action()
            assert result is True

    async def test_error_handling(self, integration_manager):
        with patch("src.services.vision_service.VisionService.analyze_screenshot",
                  AsyncMock(side_effect=VisionAPIError("API Error"))):
            result = await integration_manager.execute_vision_action()
            assert result is False
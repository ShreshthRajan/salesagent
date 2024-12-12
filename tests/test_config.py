import pytest
from src.utils.config import ConfigManager
from src.utils.exceptions import ConfigurationError
import os

def test_config_loading():
    config = ConfigManager().config
    assert config is not None
    assert config.browser.max_concurrent > 0
    assert config.logging.level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

def test_config_validation():
    config = ConfigManager()
    assert config.config is not None

def test_missing_api_keys(monkeypatch):
    # Reset singleton
    ConfigManager._instance = None
    ConfigManager._config = None

    # Remove the environment variable
    monkeypatch.delenv('APOLLO_API_KEY', raising=False)

    # This should raise ConfigurationError
    with pytest.raises(ConfigurationError):
        config = ConfigManager()
        config.validate_config()
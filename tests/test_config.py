import pytest
import logging
from src.utils.config import ConfigManager
from src.utils.exceptions import ConfigurationError
import os

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
def clean_env():
    """Reset environment before each test"""
    # Store original env
    original_env = dict(os.environ)
    
    # Remove API keys
    for key in ['APOLLO_API_KEY', 'ROCKETREACH_API_KEY', 'OPENAI_API_KEY']:
        os.environ.pop(key, None)
    
    yield
    
    # Restore original env
    os.environ.clear()
    os.environ.update(original_env)

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the ConfigManager singleton"""
    ConfigManager._instance = None
    ConfigManager._config = None
    yield

def test_config_loading(monkeypatch):
    """Test successful config loading"""
    monkeypatch.setenv('APOLLO_API_KEY', 'test')
    monkeypatch.setenv('ROCKETREACH_API_KEY', 'test')
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    
    config = ConfigManager().config
    assert config is not None
    assert config.browser.max_concurrent > 0
    assert config.logging.level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

def test_config_validation(monkeypatch):
    """Test config validation with valid keys"""
    monkeypatch.setenv('APOLLO_API_KEY', 'test')
    monkeypatch.setenv('ROCKETREACH_API_KEY', 'test')
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    
    config = ConfigManager()
    assert config.config is not None

def test_missing_api_keys():
    """Test error handling for missing API keys"""
    # Environment is clean from fixture
    with pytest.raises(ConfigurationError) as exc_info:
        ConfigManager()
    
    assert "Missing required API keys" in str(exc_info.value)

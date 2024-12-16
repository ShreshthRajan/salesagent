from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from src.utils.exceptions import ConfigurationError
import os

import logging

logger = logging.getLogger(__name__)

class OpenAIConfig(BaseModel):
    base_url: str
    rate_limit: int
    model: str
    temperature: float
    api_key: Optional[str] = None

class APIConfig(BaseModel):
    base_url: str
    rate_limit: int
    api_key: Optional[str] = None

class BrowserConfig(BaseModel):
    max_concurrent: int
    timeout: int
    retry_attempts: int

class ProxyConfig(BaseModel):
    rotation_interval: int
    max_failures: int

class LoggingConfig(BaseModel):
    level: str
    format: str

class ApiConfigs(BaseModel):
    apollo: APIConfig
    rocketreach: APIConfig
    openai: OpenAIConfig

class Config(BaseModel):
    api: ApiConfigs
    browser: BrowserConfig
    proxies: ProxyConfig
    logging: LoggingConfig

class ConfigManager:
    _instance: Optional['ConfigManager'] = None
    _config: Optional[Config] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._check_api_keys()  # Check BEFORE loading config
            self._load_config()

    def _check_api_keys(self):
        """Check for required API keys"""
        missing_keys = []
        for key in ['APOLLO_API_KEY', 'ROCKETREACH_API_KEY', 'OPENAI_API_KEY']:
            if not os.environ.get(key):
                missing_keys.append(key)
        
        if missing_keys:
            raise ConfigurationError(f"Missing required API keys: {', '.join(missing_keys)}")

    def _load_config(self):
        """Load configuration from file"""
        config_path = Path(__file__).parent.parent.parent / 'config' / 'config.yaml'
        
        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        if 'api' not in config_data:
            config_data['api'] = {}

        for service in ['apollo', 'rocketreach', 'openai']:
            if service not in config_data['api']:
                config_data['api'][service] = {}
            
            config_data['api'][service]['api_key'] = os.environ[f'{service.upper()}_API_KEY']
            
            if service == 'openai':
                config_data['api']['openai'].update({
                    'model': 'gpt-4-1106-preview',
                    'temperature': 0.1,
                    'base_url': 'https://api.openai.com/v1',
                    'rate_limit': 50
                })

        self._config = Config(**config_data)

    @property
    def config(self) -> Config:
        """Access the configuration"""
        if self._config is None:
            raise ConfigurationError("Configuration not initialized")
        return self._config
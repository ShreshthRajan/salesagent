from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from src.utils.exceptions import ConfigurationError
import os

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
            self._load_config()
            self.validate_config()

    def _load_config(self):
        load_dotenv()
        config_path = Path(__file__).parent.parent.parent / 'config' / 'config.yaml'

        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        # Add environment variables
        if 'api' not in config_data:
            config_data['api'] = {}
        for service in ['apollo', 'rocketreach', 'openai']:
            if service not in config_data['api']:
                config_data['api'][service] = {}
            config_data['api'][service]['api_key'] = os.getenv(f'{service.upper()}_API_KEY')

        self._config = Config(**config_data)

    def validate_config(self) -> None:
        """Validate configuration values"""
        try:
            if self.config.browser.max_concurrent < 1:
                raise ConfigurationError("max_concurrent must be at least 1")
            if self.config.proxies.rotation_interval < 0:
                raise ConfigurationError("rotation_interval must be positive")
            # Add validation for API keys
            if not self.config.api.apollo.api_key:
                raise ConfigurationError("APOLLO_API_KEY not found in environment")
            if not self.config.api.rocketreach.api_key:
                raise ConfigurationError("ROCKETREACH_API_KEY not found in environment")
            if not self.config.api.openai.api_key:
                raise ConfigurationError("OPENAI_API_KEY not found in environment")
        except Exception as e:
            raise ConfigurationError(f"Configuration validation failed: {str(e)}")

    @property
    def config(self) -> Config:
        return self._config
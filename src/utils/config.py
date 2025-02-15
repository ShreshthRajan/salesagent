# src/utils/config.py
from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, ConfigDict, Field
from dotenv import load_dotenv
from src.utils.exceptions import ConfigurationError
import os
import aiohttp
from pydantic import BaseModel, Field
from typing import Optional

import logging

logger = logging.getLogger(__name__)

class OpenAIConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    api_key: str = "test-key"
    base_url: str = "https://api.openai.com/v1"
    rate_limit: int = 50
    model: str = "gpt-4-vision-preview"
    temperature: float = 0.1

class APIConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    base_url: str
    rate_limit: int
    api_key: Optional[str] = None

class BrowserConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    max_concurrent: int = 5
    timeout: int = 30000
    retry_attempts: int = 3

class ProxyConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    rotation_interval: int = 300
    max_failures: int = 3

class LoggingConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    level: str = "INFO"
    format: str = "json"

class ApiConfigs(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    apollo: APIConfig = Field(default_factory=lambda: APIConfig(base_url="", rate_limit=0))
    rocketreach: APIConfig = Field(default_factory=lambda: APIConfig(base_url="", rate_limit=0))
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)

class Config(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    api: ApiConfigs = Field(default_factory=ApiConfigs)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    proxies: ProxyConfig = Field(default_factory=ProxyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

class ConfigManager:
    _instance: Optional['ConfigManager'] = None
    _config: Optional[Config] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        We only load config and check for MISSING env variables here.
        We do NOT validate the keys themselves during init (so invalid
        keys won't stop the entire session).
        """
        if not self._initialized:
            self._check_api_keys()  # Raises if any are entirely missing
            self._load_config()
            self._initialized = True

    async def initialize(self):
        """
        Initialize without forcing the API key validations.
        You can still manually call `await self.validate_api_keys()` 
        if you want to check all keys at once.
        """
        if not self._initialized:
            self._check_api_keys()
            self._load_config()
            self._initialized = True
        # Removed the call to `await self.validate_api_keys()`
        return self

    def _check_api_keys(self):
        """
        Check for presence of required API keys in environment.
        Raise if any keys are MISSING (but not if they are invalid).
        
        The OpenAI API key is required for vision services and will be 
        loaded into the Config.api.openai configuration.
        """
        missing_keys = []
        for key in ['APOLLO_API_KEY', 'ROCKETREACH_API_KEY', 'OPENAI_API_KEY']:
            if not os.environ.get(key):
                missing_keys.append(key)
        
        if missing_keys:
            raise ConfigurationError(
                f"Missing required API keys: {', '.join(missing_keys)}"
            )
            
        # Add OpenAI config validation
        if not os.environ.get('OPENAI_API_KEY'):
            raise ConfigurationError("Missing required OpenAI API key")
    async def validate_api_keys(self):
        """
        Validate Apollo and RocketReach API keys by making real requests.
        If Apollo fails, we raise an exception here. 
        If you want your tests to keep going, either handle these exceptions
        or call the key validations individually in your test.
        """
        async with aiohttp.ClientSession() as session:
            # Test Apollo API key
            apollo_url = f"{self.config.api.apollo.base_url}/organizations/search"
            apollo_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api.apollo.api_key}"
            }
            
            logger.debug(f"Testing Apollo API with URL: {apollo_url}")
            logger.debug(f"Apollo Headers: {apollo_headers}")
            
            try:
                async with session.get(apollo_url, headers=apollo_headers) as response:
                    response_text = await response.text()
                    logger.debug(f"Apollo Response Status: {response.status}")
                    logger.debug(f"Apollo Response: {response_text}")
                    
                    if response.status == 401:
                        raise ConfigurationError("Invalid Apollo API key")
                    elif response.status != 200:
                        raise ConfigurationError(f"Apollo API error: {response.status}")
                    logger.info("Apollo API key validated successfully")
            except Exception as e:
                raise ConfigurationError(f"Apollo API key validation failed: {str(e)}")

            # RocketReach test
            rr_url = f"{self.config.api.rocketreach.base_url}/account"
            rr_headers = {
                "Content-Type": "application/json",
                "Api-Key": self.config.api.rocketreach.api_key
            }
            
            logger.debug(f"Testing RocketReach API with URL: {rr_url}")
            logger.debug(f"RocketReach Headers: {rr_headers}")
            
            try:
                async with session.get(rr_url, headers=rr_headers) as response:
                    response_text = await response.text()
                    logger.debug(f"RocketReach Response Status: {response.status}")
                    logger.debug(f"RocketReach Response: {response_text}")
                    
                    if response.status in [401, 403]:
                        raise ConfigurationError("Invalid RocketReach API key")
                    elif response.status != 200:
                        raise ConfigurationError(f"RocketReach API error: {response.status}")
                    logger.info("RocketReach API key validated successfully")
            except Exception as e:
                raise ConfigurationError(f"RocketReach API key validation failed: {str(e)}")
            
    def _load_config(self):
        """Load configuration from YAML file and environment variables."""
        config_path = Path(__file__).parent.parent.parent / 'config' / 'config.yaml'
        
        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        if 'api' not in config_data:
            config_data['api'] = {}

        for service in ['apollo', 'rocketreach', 'openai']:
            if service not in config_data['api']:
                config_data['api'][service] = {}
            
            # Inject the API keys from environment
            config_data['api'][service]['api_key'] = os.environ[f'{service.upper()}_API_KEY']
            
            if service == 'openai':
                # Provide any default settings you like for OpenAI
                config_data['api']['openai'].update({
                    'model': 'gpt-4-1106-preview',
                    'temperature': 0.1,
                    'base_url': 'https://api.openai.com/v1',
                    'rate_limit': 50
                })

        self._config = Config(**config_data)

    @property
    def config(self) -> Config:
        """Access the configuration object once it's loaded."""
        if self._config is None:
            raise ConfigurationError("Configuration not initialized")
        return self._config

import asyncio
from src.utils.config import ConfigManager
from src.utils.logging import setup_logging
from src.utils.exceptions import SalesAgentException
import logging
import sys

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def validate_setup():
    """Validate environment and API keys"""
    try:
        config_manager = ConfigManager()
        await config_manager.validate_api_keys()
        return True
    except Exception as e:
        logger.error(f"Setup validation failed: {str(e)}")
        return False

async def main():
    try:
        # Setup logging
        logger = setup_logging()
        
        # First validate API keys
        if not await validate_setup():
            logger.error("API key validation failed. Please check your credentials.")
            sys.exit(1)

        # Load and validate config
        config_manager = ConfigManager()
        config_manager.validate_config()

        logger.info("Sales agent initialized", extra={
            "apollo_rate_limit": config_manager.config.api['apollo'].rate_limit,
            "browser_concurrent": config_manager.config.browser.max_concurrent
        })
    except SalesAgentException as e:
        logger.error(f"Sales agent initialization failed: {str(e)}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
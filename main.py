import asyncio
from src.utils.config import ConfigManager
from src.utils.logging import setup_logging
from src.utils.exceptions import SalesAgentException
import logging
import sys

async def main():
    try:
        # Setup logging
        logger = setup_logging()

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
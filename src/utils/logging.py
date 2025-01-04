# src/utils/logging.py
import logging
import sys
from typing import Optional
from .config import ConfigManager
from pythonjsonlogger.json import JsonFormatter

def setup_logging(level: Optional[str] = None) -> logging.Logger:
    """Setup logging configuration"""
    config = ConfigManager().config.logging

    # Create custom JSON formatter
    class CustomJsonFormatter(JsonFormatter):
        def add_fields(self, log_record, record, message_dict):
            super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
            log_record['level'] = record.levelname
            log_record['logger'] = record.name

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level or config.level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)

    if config.format.lower() == 'json':
        formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s')
    else:
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Create logger for our application
    logger = logging.getLogger('sales_agent')
    logger.setLevel(level or config.level)

    return logger
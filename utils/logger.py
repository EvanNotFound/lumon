import os
import logging
import sys
from typing import Any, Optional, Dict, Union
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Environment configuration
IS_PROD = os.getenv('ENVIRONMENT') == 'production' or os.getenv('LUMON_PROD_MODE') == 'true'
IS_DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
LOG_DIR = os.getenv('LOG_DIR', 'logs')

# Global variable that can be set from main.py
PROD_MODE = False

# Keep track of all created loggers for reconfiguration
_LOGGERS = {}

def set_production_mode(enabled: bool = True):
    """
    Set the production mode flag globally and reconfigure all existing loggers
    
    Args:
        enabled: Whether to enable production mode
    """
    global PROD_MODE
    PROD_MODE = enabled
    
    # Reconfigure all existing loggers
    for name, logger in _LOGGERS.items():
        _configure_logger(logger, name)

# ANSI color codes for terminal output
class Colors:
    RESET = '\x1b[0m'
    CYAN = '\x1b[36m'
    GREEN = '\x1b[32m'
    YELLOW = '\x1b[33m'
    RED = '\x1b[31m'
    MAGENTA = '\x1b[35m'

class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels in console output"""
    
    LEVEL_COLORS = {
        logging.DEBUG: Colors.CYAN,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.MAGENTA
    }
    
    def __init__(self, fmt: str = None, datefmt: str = None, style: str = '%'):
        super().__init__(fmt, datefmt, style)
    
    def format(self, record: logging.LogRecord) -> str:
        # Save original levelname
        original_levelname = record.levelname
        # Add color to levelname
        if record.levelno in self.LEVEL_COLORS:
            color = self.LEVEL_COLORS[record.levelno]
            record.levelname = f"{color}{record.levelname}{Colors.RESET}"
        
        result = super().format(record)
        
        # Restore original levelname
        record.levelname = original_levelname
        return result

def _configure_logger(logger: logging.Logger, name: str) -> None:
    """
    Configure or reconfigure a logger with the appropriate handlers and formatters
    
    Args:
        logger: The logger to configure
        name: The name of the logger
    """
    # Remove any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Set base log level
    is_production = IS_PROD or PROD_MODE
    logger.setLevel(logging.DEBUG if IS_DEBUG and not is_production else logging.INFO)
    logger.propagate = False  # Prevent propagation to avoid duplicate logs
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    
    # Different formatters for production and development
    if is_production:
        # Simple, clean format for production
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        # In production, set console handler to INFO level
        console_handler.setLevel(logging.INFO)
    else:
        # Colored, detailed format for development
        formatter = ColoredFormatter(
            '%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Add file handler in production
    if is_production:
        try:
            # Ensure log directory exists
            os.makedirs(LOG_DIR, exist_ok=True)
            
            # Create rotating file handler (10MB max, keep 5 backups)
            file_handler = RotatingFileHandler(
                os.path.join(LOG_DIR, f"{name}.log"),
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            
            file_formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            # Don't fail if file logging can't be set up, just log to console
            console_handler.setLevel(logging.WARNING)
            logger.addHandler(console_handler)
            logger.warning(f"Could not set up file logging: {e}")

def get_logger(name: str = None) -> logging.Logger:
    """
    Factory function to create and configure a logger.
    
    Args:
        name: The name of the logger. If None, uses the caller's module name.
        
    Returns:
        A configured logger instance
    """
    # Get the caller's module name if name is not provided
    if name is None:
        import inspect
        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])
        name = module.__name__ if module else __name__
    
    # Get or create the logger
    logger = logging.getLogger(name)
    
    # Configure the logger if it hasn't been configured yet
    if name not in _LOGGERS:
        _configure_logger(logger, name)
        _LOGGERS[name] = logger
    
    return logger

class LoggerAdapter:
    """
    Adapter class that provides a simplified interface to the standard logging module.
    This maintains backward compatibility with the original CustomLogger interface.
    """
    
    def __init__(self, name: str = None):
        self.logger = get_logger(name)
        self.name = name
    
    def debug(self, message: str, data: Any = None):
        # Skip debug logs in production mode
        if IS_PROD or PROD_MODE:
            return
            
        if data is not None:
            self.logger.debug(f"{message} {data}")
        else:
            self.logger.debug(message)
    
    def info(self, message: str, data: Any = None):
        if data is not None:
            self.logger.info(f"{message} {data}")
        else:
            self.logger.info(message)
    
    def warn(self, message: str, data: Any = None):
        if data is not None:
            self.logger.warning(f"{message} {data}")
        else:
            self.logger.warning(message)
    
    def error(self, message: str, err: Any = None):
        if err is not None:
            self.logger.error(f"{message} {err}")
        else:
            self.logger.error(message)
    
    def critical(self, message: str, err: Any = None):
        if err is not None:
            self.logger.critical(f"{message} {err}")
        else:
            self.logger.critical(message)

# Create a singleton instance for backward compatibility
logger = LoggerAdapter()

# For new code, recommend using this pattern:
# from utils.logger import get_logger
# logger = get_logger(__name__)

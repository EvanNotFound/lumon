import logging
import sys
from typing import Optional

# ANSI escape codes for colors
COLORS = {
    'DEBUG': '\033[36m',    # Cyan
    'INFO': '\033[32m',     # Green
    'WARNING': '\033[33m',  # Yellow
    'ERROR': '\033[31m',    # Red
    'CRITICAL': '\033[41m', # Red background
    'RESET': '\033[0m'      # Reset color
}

class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels"""
    def format(self, record):
        # Add colors if not windows (as windows terminal might not support ANSI)
        if not sys.platform.startswith('win'):
            levelname = record.levelname
            if levelname in COLORS:
                record.levelname = f"{COLORS[levelname]}{levelname}{COLORS['RESET']}"
        return super().format(record)

def setup_logger(name: str, level: Optional[int] = logging.DEBUG) -> logging.Logger:
    """
    Set up a colored logger with the specified name and level.
    
    Args:
        name (str): The name of the logger
        level (int, optional): The logging level. Defaults to DEBUG.
    
    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Only add handler if the logger doesn't already have handlers
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

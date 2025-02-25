import os
import logging
from datetime import datetime

# Environment configuration
IS_PROD = os.getenv('ENVIRONMENT') == 'production'
IS_DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

# ANSI color codes
class Colors:
    RESET = '\x1b[0m'
    CYAN = '\x1b[36m'
    GREEN = '\x1b[32m'
    YELLOW = '\x1b[33m'
    RED = '\x1b[31m'

def colorize_log_level(level: str, color: str) -> str:
    return f"{color}{level}{Colors.RESET}"

class CustomLogger:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG if IS_DEBUG else logging.INFO)
        
        # Create console handler if none exists
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            # Prevent propagation to root logger to avoid duplicate logs
            self.logger.propagate = False
            self.logger.addHandler(handler)

    def _format_message(self, level: str, color: str, message: str) -> str:
        colored_level = colorize_log_level(level, color)
        timestamp = datetime.now().isoformat()
        return f"[{timestamp}] {colored_level}: {message}"

    def debug(self, message: str, data: any = None):
        if IS_DEBUG:
            formatted = self._format_message("DEBUG", Colors.CYAN, message)
            self.logger.debug(formatted + (f" {data}" if data else ""))

    def info(self, message: str, data: any = None):
        if IS_PROD:
            self.logger.info(f"{message}{' ' + str(data) if data else ''}")
        else:
            formatted = self._format_message("INFO", Colors.GREEN, message)
            self.logger.info(formatted + (f" {data}" if data else ""))

    def warn(self, message: str, data: any = None):
        if IS_PROD:
            self.logger.warning(f"{message}{' ' + str(data) if data else ''}")
        else:
            formatted = self._format_message("WARN", Colors.YELLOW, message)
            self.logger.warning(formatted + (f" {data}" if data else ""))

    def error(self, message: str, err: any = None):
        if IS_PROD:
            self.logger.error(f"{message}{' ' + str(err) if err else ''}")
        else:
            formatted = self._format_message("ERROR", Colors.RED, message)
            self.logger.error(formatted + (f" {err}" if err else ""))

# Create a singleton instance
logger = CustomLogger()

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional
import os

class BotLogger:
    """Centralized logging configuration for the Discord bot"""
    
    def __init__(self, name: str = "discord_bot", log_level: str = "INFO", log_file: str = "bot.log"):
        self.name = name
        self.log_level = getattr(logging, log_level.upper())
        self.log_file = log_file
        self._logger: Optional[logging.Logger] = None
        
    def setup_logging(self) -> logging.Logger:
        """Setup and configure logging"""
        if self._logger:
            return self._logger
            
        # Create logger
        self._logger = logging.getLogger(self.name)
        self._logger.setLevel(self.log_level)
        
        # Prevent duplicate handlers
        if self._logger.handlers:
            return self._logger
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(simple_formatter)
        
        # File handler with rotation
        file_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        
        # Error file handler
        error_handler = RotatingFileHandler(
            'bot_errors.log',
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        
        # Add handlers
        self._logger.addHandler(console_handler)
        self._logger.addHandler(file_handler)
        self._logger.addHandler(error_handler)
        
        return self._logger
    
    def get_logger(self, module_name: str = None) -> logging.Logger:
        """Get a logger for a specific module"""
        if not self._logger:
            self.setup_logging()
        
        if module_name:
            return logging.getLogger(f"{self.name}.{module_name}")
        return self._logger

# Global logger instance
bot_logger = BotLogger()
logger = bot_logger.setup_logging()

# Module-specific loggers
def get_logger(module_name: str) -> logging.Logger:
    """Get a logger for a specific module"""
    return bot_logger.get_logger(module_name)

# Convenience functions for different log levels
def log_info(message: str, module: str = "main") -> None:
    """Log info message"""
    get_logger(module).info(message)

def log_warning(message: str, module: str = "main") -> None:
    """Log warning message"""
    get_logger(module).warning(message)

def log_error(message: str, module: str = "main", exc_info: bool = False) -> None:
    """Log error message"""
    get_logger(module).error(message, exc_info=exc_info)

def log_debug(message: str, module: str = "main") -> None:
    """Log debug message"""
    get_logger(module).debug(message)
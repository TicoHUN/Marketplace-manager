import traceback
from typing import Optional, Dict, Any
from datetime import datetime

# Try to import discord, fallback if not available
try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    # Create mock discord classes for testing
    class discord:
        class Interaction:
            pass
        class Embed:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
        class Color:
            @staticmethod
            def red():
                return "red"
        errors = type('errors', (), {
            'Forbidden': Exception,
            'NotFound': Exception,
            'HTTPException': Exception
        })()

try:
    from logger_config import get_logger
    logger = get_logger("error_handler")
except ImportError:
    # Fallback logger
    class logger:
        @staticmethod
        def error(msg, exc_info=False): print(f"ERROR: {msg}")
        @staticmethod
        def warning(msg): print(f"WARNING: {msg}")
        @staticmethod
        def info(msg): print(f"INFO: {msg}")

class BotError(Exception):
    """Base exception class for bot-specific errors"""
    def __init__(self, message: str, user_friendly: bool = True, log_level: str = "ERROR"):
        self.message = message
        self.user_friendly = user_friendly
        self.log_level = log_level
        super().__init__(message)

class ValidationError(BotError):
    """Error for input validation failures"""
    def __init__(self, message: str):
        super().__init__(message, user_friendly=True, log_level="WARNING")

class DatabaseError(BotError):
    """Error for database operation failures"""
    def __init__(self, message: str, user_friendly: bool = False):
        super().__init__(message, user_friendly=user_friendly, log_level="ERROR")

class PermissionError(BotError):
    """Error for permission-related failures"""
    def __init__(self, message: str):
        super().__init__(message, user_friendly=True, log_level="WARNING")

class ConfigurationError(BotError):
    """Error for configuration-related failures"""
    def __init__(self, message: str):
        super().__init__(message, user_friendly=False, log_level="CRITICAL")

class ErrorHandler:
    """Centralized error handling for the Discord bot"""
    
    def __init__(self):
        self.error_count = 0
        self.last_error_time = None
    
    async def handle_interaction_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Handle errors that occur during Discord interactions"""
        self.error_count += 1
        self.last_error_time = datetime.utcnow()
        
        # Log the error
        error_msg = f"Interaction error in {interaction.command.name if interaction.command else 'unknown'}: {error}"
        logger.error(error_msg, exc_info=True)
        
        # Determine user-friendly message
        if isinstance(error, BotError):
            user_message = error.message if error.user_friendly else "An internal error occurred. Please try again later."
            log_level = error.log_level
        elif isinstance(error, discord.errors.Forbidden):
            user_message = "I don't have permission to perform this action. Please contact an administrator."
            log_level = "WARNING"
        elif isinstance(error, discord.errors.NotFound):
            user_message = "The requested resource was not found. It may have been deleted."
            log_level = "WARNING"
        elif isinstance(error, discord.errors.HTTPException):
            user_message = "A Discord API error occurred. Please try again."
            log_level = "ERROR"
        else:
            user_message = "An unexpected error occurred. Please try again later."
            log_level = "ERROR"
        
        # Send error response to user
        try:
            embed = discord.Embed(
                title="❌ Error",
                description=user_message,
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as send_error:
            logger.error(f"Failed to send error message to user: {send_error}")
    
    async def handle_command_error(self, ctx, error: Exception) -> None:
        """Handle errors that occur during command execution"""
        self.error_count += 1
        self.last_error_time = datetime.utcnow()
        
        # Log the error
        error_msg = f"Command error in {ctx.command}: {error}"
        logger.error(error_msg, exc_info=True)
        
        # Send user-friendly error message
        try:
            if isinstance(error, BotError):
                user_message = error.message if error.user_friendly else "An internal error occurred."
            else:
                user_message = "An unexpected error occurred. Please try again later."
            
            embed = discord.Embed(
                title="❌ Error",
                description=user_message,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            
        except Exception as send_error:
            logger.error(f"Failed to send error message to user: {send_error}")
    
    def handle_generic_error(self, error: Exception, context: str = "") -> None:
        """Handle generic errors that don't involve Discord interactions"""
        self.error_count += 1
        self.last_error_time = datetime.utcnow()
        
        error_msg = f"Generic error{' in ' + context if context else ''}: {error}"
        
        if isinstance(error, BotError):
            if error.log_level == "CRITICAL":
                logger.critical(error_msg, exc_info=True)
            elif error.log_level == "ERROR":
                logger.error(error_msg, exc_info=True)
            elif error.log_level == "WARNING":
                logger.warning(error_msg)
            else:
                logger.info(error_msg)
        else:
            logger.error(error_msg, exc_info=True)
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        return {
            "total_errors": self.error_count,
            "last_error_time": self.last_error_time,
            "uptime_hours": (datetime.utcnow() - self.last_error_time).total_seconds() / 3600 if self.last_error_time else None
        }

# Global error handler instance
error_handler = ErrorHandler()

# Convenience functions for different error types
async def handle_interaction_error(interaction: discord.Interaction, error: Exception) -> None:
    """Handle interaction errors"""
    await error_handler.handle_interaction_error(interaction, error)

async def handle_command_error(ctx, error: Exception) -> None:
    """Handle command errors"""
    await error_handler.handle_command_error(ctx, error)

def handle_error(error: Exception, context: str = "") -> None:
    """Handle generic errors"""
    error_handler.handle_generic_error(error, context)

# Decorator for automatic error handling
def handle_errors(user_friendly_message: str = None):
    """Decorator to automatically handle errors in functions"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if len(args) > 0 and isinstance(args[0], discord.Interaction):
                    await handle_interaction_error(args[0], e)
                else:
                    handle_error(e, func.__name__)
                raise
        
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handle_error(e, func.__name__)
                raise
        
        if hasattr(func, '__code__') and func.__code__.co_flags & 0x80:  # Check if coroutine
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
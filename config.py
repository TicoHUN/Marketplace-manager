import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class BotConfig:
    """Centralized configuration for the Discord bot"""
    
    # Discord Configuration
    BOT_TOKEN: str
    
    # Channel IDs
    SELL_CHANNEL_ID: int = 1394786079995072704
    TRADE_CHANNEL_ID: int = 1394786078552227861
    AUCTION_CHANNEL_ID: int = 1394786069534216353
    AUCTION_FORUM_ID: int = 1394800803197354014
    GIVEAWAY_CHANNEL_ID: int = 1394786061540130879
    GIVEAWAYS_CHANNEL_ID: int = 1394786059635654817
    GIVEAWAY_REVIEW_ID: int = 1394786040438587503
    SUPPORT_CHANNEL_ID: int = 1394786056699641977
    TRADELOG_CHANNEL_ID: int = 1394786041243762729
    BOT_CHANNEL_ID: int = 1394786046109024428
    SELL_TRADE_CHANNEL_ID: int = 1394786077180694529
    
    # Role IDs
    MEMBER_ROLE_ID: int = 1394786020842799235
    
    # Database Configuration
    MYSQL_HOST: str = "localhost"
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "bot_database"
    MYSQL_PORT: int = 3306
    
    # Bot Settings
    IMAGE_UPLOAD_TIMEOUT: int = 90
    MAX_USER_LISTINGS: int = 3
    CHANNEL_INACTIVITY_TIMEOUT: int = 7200  # 2 hours
    DEAL_CONFIRMATION_TIMEOUT: int = 3600   # 1 hour
    
    # Connection Pool Settings
    DB_POOL_SIZE: int = 10
    DB_POOL_RESET_SESSION: bool = True
    
    @classmethod
    def from_env(cls) -> 'BotConfig':
        """Create configuration from environment variables"""
        bot_token = os.getenv('DISCORD_BOT_TOKEN')
        if not bot_token:
            raise ValueError("DISCORD_BOT_TOKEN environment variable is not set!")
        
        if not bot_token.startswith(('Bot ', 'Bearer ')) and '.' not in bot_token:
            raise ValueError("DISCORD_BOT_TOKEN appears to be invalid format!")
        
        return cls(
            BOT_TOKEN=bot_token,
            MYSQL_HOST=os.getenv('MYSQL_HOST', 'localhost'),
            MYSQL_USER=os.getenv('MYSQL_USER', 'root'),
            MYSQL_PASSWORD=os.getenv('MYSQL_PASSWORD', ''),
            MYSQL_DATABASE=os.getenv('MYSQL_DATABASE', 'bot_database'),
            MYSQL_PORT=int(os.getenv('MYSQL_PORT', '3306')),
        )
    
    def validate(self) -> None:
        """Validate configuration values"""
        if not self.MYSQL_PASSWORD:
            raise ValueError("MYSQL_PASSWORD environment variable not set")
        
        if self.IMAGE_UPLOAD_TIMEOUT <= 0:
            raise ValueError("IMAGE_UPLOAD_TIMEOUT must be positive")
        
        if self.MAX_USER_LISTINGS <= 0:
            raise ValueError("MAX_USER_LISTINGS must be positive")

# Global configuration instance
config = BotConfig.from_env()
config.validate()
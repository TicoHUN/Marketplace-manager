import os
from dataclasses import dataclass
from typing import Optional

# Try to load dotenv, fallback if not available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, use environment variables directly
    pass

@dataclass
class BotConfig:
    """Centralized configuration for the Discord bot"""
    
    # Discord Configuration
    BOT_TOKEN: str
    
    # Channel IDs
    SELL_CHANNEL_ID: int = 1390752480933052506  # #sell-cars
    TRADE_CHANNEL_ID: int = 1390752375899426836  # #trade-cars
    AUCTION_CHANNEL_ID: int = 1392094616848957510  # #make-auction
    AUCTION_FORUM_ID: int = 1390752554996207706  # #auction-house forum
    GIVEAWAY_CHANNEL_ID: int = 1391746494121513040  # #make-giveaways
    GIVEAWAYS_CHANNEL_ID: int = 1391746430028480553  # #giveaways
    GIVEAWAY_REVIEW_ID: int = 1392464608027218011  # #giveaway-review
    SUPPORT_CHANNEL_ID: int = 1391745107635736647  # #support
    TRADELOG_CHANNEL_ID: int = 1391944967928414339  # #tradelog-bot
    BOT_CHANNEL_ID: int = 1391925046657814689  # #bot (log channel)
    SELL_TRADE_CHANNEL_ID: int = 1391717704661995571  # #make-sell-trade
    RULES_CHANNEL_ID: int = 1390745679646818457  # #rules
    ENDED_AUCTIONS_THREAD_ID: int = 1392667262560899163  # Thread for ended auctions
    
    # Role IDs
    MEMBER_ROLE_ID: int = 1392239599496990791  # @Member role
    
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
from typing import Union, Optional, List, Tuple
import re
from dataclasses import dataclass

@dataclass
class ValidationResult:
    """Result of a validation operation"""
    is_valid: bool
    value: Optional[Union[str, int, float]] = None
    error_message: Optional[str] = None

class InputValidator:
    """Comprehensive input validation for bot operations"""
    
    # Validation patterns
    PRICE_PATTERN = re.compile(r'^\d{1,10}$')
    CAR_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9\s\-\(\)\.\/]{2,100}$')
    USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.]{2,32}$')
    
    # Limits
    MIN_PRICE = 1
    MAX_PRICE = 100_000_000
    MIN_CAR_NAME_LENGTH = 2
    MAX_CAR_NAME_LENGTH = 100
    MIN_DESCRIPTION_LENGTH = 0
    MAX_DESCRIPTION_LENGTH = 500
    MIN_AUCTION_DURATION = 5  # minutes
    MAX_AUCTION_DURATION = 10080  # 1 week in minutes
    
    @classmethod
    def validate_price(cls, price_input: str) -> ValidationResult:
        """Validate and parse price input"""
        if not price_input:
            return ValidationResult(False, None, "Price cannot be empty")
        
        # Clean price input
        cleaned_price = price_input.replace('$', '').replace(',', '').replace(' ', '').strip()
        
        # Check format
        if not cls.PRICE_PATTERN.match(cleaned_price):
            return ValidationResult(False, None, "Price must contain only numbers")
        
        try:
            price = int(cleaned_price)
        except ValueError:
            return ValidationResult(False, None, "Invalid price format")
        
        # Check range
        if price < cls.MIN_PRICE:
            return ValidationResult(False, None, f"Price must be at least ${cls.MIN_PRICE:,}")
        
        if price > cls.MAX_PRICE:
            return ValidationResult(False, None, f"Price cannot exceed ${cls.MAX_PRICE:,}")
        
        return ValidationResult(True, price, None)
    
    @classmethod
    def validate_car_name(cls, car_name: str) -> ValidationResult:
        """Validate car name input"""
        if not car_name:
            return ValidationResult(False, None, "Car name cannot be empty")
        
        car_name = car_name.strip()
        
        # Check length
        if len(car_name) < cls.MIN_CAR_NAME_LENGTH:
            return ValidationResult(False, None, f"Car name must be at least {cls.MIN_CAR_NAME_LENGTH} characters")
        
        if len(car_name) > cls.MAX_CAR_NAME_LENGTH:
            return ValidationResult(False, None, f"Car name cannot exceed {cls.MAX_CAR_NAME_LENGTH} characters")
        
        # Check pattern (allow letters, numbers, spaces, and common symbols)
        if not cls.CAR_NAME_PATTERN.match(car_name):
            return ValidationResult(False, None, "Car name contains invalid characters")
        
        return ValidationResult(True, car_name, None)
    
    @classmethod
    def validate_description(cls, description: str) -> ValidationResult:
        """Validate description input"""
        if description is None:
            description = ""
        
        description = description.strip()
        
        # Check length
        if len(description) > cls.MAX_DESCRIPTION_LENGTH:
            return ValidationResult(False, None, f"Description cannot exceed {cls.MAX_DESCRIPTION_LENGTH} characters")
        
        return ValidationResult(True, description, None)
    
    @classmethod
    def validate_auction_duration(cls, hours: int, minutes: int = 0) -> ValidationResult:
        """Validate auction duration"""
        total_minutes = hours * 60 + minutes
        
        if total_minutes < cls.MIN_AUCTION_DURATION:
            return ValidationResult(False, None, f"Auction duration must be at least {cls.MIN_AUCTION_DURATION} minutes")
        
        if total_minutes > cls.MAX_AUCTION_DURATION:
            return ValidationResult(False, None, f"Auction duration cannot exceed {cls.MAX_AUCTION_DURATION // 60} hours")
        
        return ValidationResult(True, total_minutes, None)
    
    @classmethod
    def validate_user_id(cls, user_id: Union[str, int]) -> ValidationResult:
        """Validate Discord user ID"""
        try:
            user_id_int = int(user_id)
            if user_id_int <= 0:
                return ValidationResult(False, None, "User ID must be positive")
            return ValidationResult(True, user_id_int, None)
        except (ValueError, TypeError):
            return ValidationResult(False, None, "Invalid user ID format")
    
    @classmethod
    def validate_channel_id(cls, channel_id: Union[str, int]) -> ValidationResult:
        """Validate Discord channel ID"""
        try:
            channel_id_int = int(channel_id)
            if channel_id_int <= 0:
                return ValidationResult(False, None, "Channel ID must be positive")
            return ValidationResult(True, channel_id_int, None)
        except (ValueError, TypeError):
            return ValidationResult(False, None, "Invalid channel ID format")
    
    @classmethod
    def sanitize_input(cls, text: str, max_length: int = 500) -> str:
        """Sanitize text input by removing potentially harmful content"""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length-3] + "..."
        
        return text

class SecurityValidator:
    """Security-focused validation for detecting risky content"""
    
    # Updated from the original utils.py
    RISKY_DM_PHRASES = [
        "dm me", "check dm", "i sent it in dm", "let's finish in dm", "send it on discord",
        "message me", "pm me", "private message", "direct message", "text me privately",
        "continue in dm", "finish in dm", "move to dm", "talk in dm", "add me quick",
        "don't tell anyone", "outside deal", "trust me", "i'll go first", "send now",
        "whatsapp", "telegram", "snapchat", "join my server", "click here", "http://",
        "https://", "invite.gg", "discord.gg/", "qr code", "quick trade", "fast deal",
        "admin said", "mod said", "i got scammed"
    ]

    PAYMENT_PLATFORMS = [
        "paypal", "revolut", "cashapp", "venmo", "crypto", "bitcoin", "ethereum",
        "gift card", "steam card", "google play card", "money transfer", "western union",
        "zelle", "apple pay", "google pay", "stripe", "square", "robinhood", "btc",
        "eth", "skrill", "bank transfer", "iban", "wise", "real money", "money trade",
        "rmt", "usd", "eur", "cash", "payment", "bank", "nitro for free", "free nitro",
        "steam gift"
    ]
    
    @classmethod
    def check_risky_content(cls, message_content: str) -> Tuple[List[str], List[str]]:
        """
        Check if message contains risky phrases and return lists of found phrases
        Returns: (dm_flags, payment_flags)
        """
        if not message_content:
            return [], []
        
        content_lower = message_content.lower()
        
        dm_flags = [phrase for phrase in cls.RISKY_DM_PHRASES 
                   if phrase in content_lower]
        
        payment_flags = [phrase for phrase in cls.PAYMENT_PLATFORMS 
                        if phrase in content_lower]
        
        return dm_flags, payment_flags
    
    @classmethod
    def is_content_risky(cls, message_content: str) -> bool:
        """Check if content contains any risky phrases"""
        dm_flags, payment_flags = cls.check_risky_content(message_content)
        return bool(dm_flags or payment_flags)
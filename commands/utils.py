# Try to import discord, fallback if not available
try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    # Create mock discord classes for testing
    class discord:
        class Embed:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
        class Color:
            @staticmethod
            def orange():
                return "orange"

import asyncio
import io
import os
from datetime import datetime
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import aiohttp, fallback if not available
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    # Mock aiohttp for testing
    class aiohttp:
        class ClientSession:
            def __init__(self):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def get(self, url):
                return self
            async def __aenter__(self):
                return type('Response', (), {'status': 200, 'read': lambda: b'test'})()

from database_mysql import *

# Import new configuration and logging
try:
    from config import config
    from logger_config import get_logger, log_info, log_error, log_warning
    from validation import SecurityValidator
except ImportError:
    # Fallback for backward compatibility
    BOT_CHANNEL_ID = config.BOT_CHANNEL_ID
    TRADELOG_CHANNEL_ID = config.TRADELOG_CHANNEL_ID
    IMAGE_UPLOAD_TIMEOUT = 90
    
    class config:
        BOT_CHANNEL_ID = BOT_CHANNEL_ID
        TRADELOG_CHANNEL_ID = TRADELOG_CHANNEL_ID
        IMAGE_UPLOAD_TIMEOUT = IMAGE_UPLOAD_TIMEOUT
    
    def log_info(msg, module=None): print(msg)
    def log_error(msg, module=None, exc_info=False): print(f"ERROR: {msg}")
    def log_warning(msg, module=None): print(f"WARNING: {msg}")

# Initialize logger for this module
logger = get_logger("utils") if 'get_logger' in globals() else None

# Store private channel activity for inactivity check
private_channels_activity = {}

# Store messages from private channels for logging
private_channel_messages = {}

async def log_channel_messages(bot, channel):
    """Log messages from a channel before closing"""
    try:
        if channel.id in private_channel_messages:
            messages = private_channel_messages[channel.id]

            # Create a log entry
            log_content = f"=== Channel Log: {channel.name} ===\n"
            log_content += f"Channel ID: {channel.id}\n"
            log_content += f"Closed at: {datetime.utcnow()}\n\n"

            for msg_data in messages:
                message = msg_data['message']
                log_content += f"[{message.created_at}] {message.author}: {message.content}\n"

                if msg_data['flagged']:
                    log_content += f"  ⚠️ FLAGGED - DM flags: {msg_data['dm_flags']}, Payment flags: {msg_data['payment_flags']}\n"

            # Send to tradelog channel
            tradelog_channel = bot.get_channel(config.TRADELOG_CHANNEL_ID)
            if tradelog_channel:
                # Split long logs into multiple messages if needed
                if len(log_content) > 2000:
                    chunks = [log_content[i:i+2000] for i in range(0, len(log_content), 2000)]
                    for chunk in chunks:
                        await tradelog_channel.send(f"```\n{chunk}\n```")
                else:
                    await tradelog_channel.send(f"```\n{log_content}\n```")

            # Clean up stored messages
            del private_channel_messages[channel.id]

    except Exception as e:
        log_error(f"Error logging channel messages: {e}")

# Backward compatibility wrapper for check_risky_content
def check_risky_content(message_content):
    """Check if message contains risky phrases and return lists of found phrases"""
    if 'SecurityValidator' in globals():
        return SecurityValidator.check_risky_content(message_content)
    else:
        # Fallback implementation for backward compatibility
        return [], []

async def send_security_notice(channel):
    """Send a security notice to the channel"""
    security_embed = discord.Embed(
        title="🔒 Security Notice",
        description="Please keep your transaction safe and secure:\n\n"
                   "• Only exchange **in-game usernames**\n"
                   "• **Never** share personal information\n"
                   "• **Never** pay real money for in-game items\n"
                   "• Report any suspicious behavior immediately\n\n"
                   "This conversation is logged for security purposes.",
        color=discord.Color.orange()
    )
    await channel.send(embed=security_embed)

async def log_channel_messages(bot, channel):
    """Log channel messages to the tradelog channel"""
    try:
        tradelog_channel = bot.get_channel(TRADELOG_CHANNEL_ID)
        if not tradelog_channel:
            print(f"Warning: Could not find tradelog channel {TRADELOG_CHANNEL_ID}")
            return

        if channel.id not in private_channel_messages:
            print(f"No stored messages found for channel {channel.name}")
            return

        messages = private_channel_messages[channel.id]

        if not messages:
            print(f"No messages to log for channel {channel.name}")
            return

        # Create log embed
        log_embed = discord.Embed(
            title=f"📝 Channel Log: {channel.name}",
            description=f"**Channel ID:** {channel.id}\n**Total Messages:** {len(messages)}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        # Count flagged messages
        flagged_count = sum(1 for msg_data in messages if msg_data.get('flagged', False))
        if flagged_count > 0:
            log_embed.add_field(
                name="⚠️ Flagged Messages",
                value=f"{flagged_count} messages contained risky content",
                inline=False
            )

        # Send the log embed
        await tradelog_channel.send(embed=log_embed)

        # Send message content in chunks if there are any
        message_log = ""
        for i, msg_data in enumerate(messages, 1):
            try:
                message = msg_data['message']
                timestamp = message.created_at.strftime("%H:%M:%S")
                content = message.content if message.content else "[No text content]"

                # Add attachments info
                if message.attachments:
                    content += f" [Attachments: {len(message.attachments)}]"

                # Add flag indicators
                flag_indicators = ""
                if msg_data.get('flagged', False):
                    if msg_data.get('dm_flags'):
                        flag_indicators += " 🔴"
                    if msg_data.get('payment_flags'):
                        flag_indicators += " 💰"

                log_line = f"{i}. [{timestamp}] {message.author.display_name}: {content}{flag_indicators}\n"

                # Check if adding this line would exceed Discord's 2000 character limit
                if len(message_log + log_line) > 1900:  # Leave some buffer
                    if message_log:
                        await tradelog_channel.send(f"```\n{message_log}```")
                    message_log = log_line
                else:
                    message_log += log_line

            except Exception as e:
                print(f"Error processing message {i}: {e}")
                continue

        # Send any remaining messages
        if message_log:
            await tradelog_channel.send(f"```\n{message_log}```")

        # Clean up stored messages
        del private_channel_messages[channel.id]
        print(f"Successfully logged {len(messages)} messages from {channel.name}")

    except Exception as e:
        print(f"Error logging channel messages: {e}")

async def save_image_to_bot_channel(bot, image_url, listing_type, car_name, username):
    """Save image to bot channel and return the saved image URL"""
    try:
        bot_channel = bot.get_channel(config.BOT_CHANNEL_ID)
        if not bot_channel:
            log_error(f"Could not find bot channel {config.BOT_CHANNEL_ID}")
            return image_url

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    image_file = discord.File(io.BytesIO(image_data), filename=f"{listing_type}_{car_name}_{username}.png")

                    log_message = await bot_channel.send(
                        f"📷 **{listing_type.title()} Image**\n"
                        f"**Car:** {car_name}\n"
                        f"**User:** {username}\n"
                        f"**Time:** <t:{int(datetime.utcnow().timestamp())}:F>",
                        file=image_file
                    )

                    if log_message.attachments:
                        saved_url = log_message.attachments[0].url
                        log_info(f"Saved {listing_type} image to bot channel: {saved_url}")
                        return saved_url

    except Exception as e:
        log_error(f"Error saving image to bot channel: {e}")

    return image_url

async def listing_timeout(user_id, channel, listing_type):
    """Handle timeout for pending listings"""
    await asyncio.sleep(config.IMAGE_UPLOAD_TIMEOUT)

    # Check if listing is still pending
    pending_listing = get_pending_listing(user_id, listing_type)
    if pending_listing:
        # Remove the pending listing
        remove_pending_listing(user_id, listing_type)

        try:
            # Create timeout embed
            timeout_embed = discord.Embed(
                title="⏰ Listing Timeout",
                description=f"Your {listing_type} listing has been cancelled because no image was uploaded within {IMAGE_UPLOAD_TIMEOUT} seconds.\n\nYou can now create a new {listing_type} listing.",
                color=discord.Color.red()
            )

            # Try to send a DM first
            dm_sent = False
            try:
                if hasattr(channel, 'guild') and channel.guild:
                    user = channel.guild.get_member(user_id)
                    if user:
                        await user.send(embed=timeout_embed)
                        dm_sent = True
                        print(f"Sent timeout DM to user {user.display_name}")
            except Exception as dm_error:
                print(f"Could not send timeout DM to user {user_id}: {dm_error}")

            # If DM failed, send a brief message in channel that deletes quickly
            if not dm_sent and hasattr(channel, 'send'):
                await channel.send(f"<@{user_id}> Your {listing_type} listing has timed out. Check your DMs for details.", delete_after=5)

        except Exception as e:
            print(f"Error sending timeout notification to user {user_id}: {e}")

        print(f"Listing timeout: {listing_type} for user {user_id} - pending listing removed")

def format_price(price_str):
    """Format price to show K or M for thousands/millions"""
    try:
        if not price_str or not isinstance(price_str, str):
            return str(price_str) if price_str else "0"

        # Remove common currency symbols and spaces
        clean_price = price_str.replace('$', '').replace('€', '').replace('£', '').replace('HUF', '').replace(',', '').replace(' ', '')

        # Try to extract just the number
        import re
        numbers = re.findall(r'\d+', clean_price)

        if not numbers:
            return price_str  # Return original if no numbers found

        try:
            price_num = int(numbers[0])  # Take the first number found

            if price_num >= 1000000:
                # Format as millions
                formatted = f"{price_num / 1000000:.1f}M"
                # Remove .0 if it's a whole number
                if formatted.endswith('.0M'):
                    formatted = formatted[:-3] + 'M'
            elif price_num >= 1000:
                # Format as thousands
                formatted = f"{price_num / 1000:.0f}K"
            else:
                formatted = str(price_num)

            # Add back currency info if it was in original
            if 'HUF' in price_str:
                return f"{formatted} HUF"
            elif '$' in price_str:
                return f"${formatted}"
            elif '€' in price_str:
                return f"€{formatted}"
            elif '£' in price_str:
                return f"£{formatted}"
            else:
                return formatted

        except (ValueError, OverflowError):
            return price_str  # Return original if conversion fails
    except Exception as e:
        print(f"Error in format_price: {e}")
        return str(price_str) if price_str else "0"

# Legacy functions for ba# Legacy functions for backward compatibility - now using database
def load_json_data(filename):
    """Legacy function - now returns data from database"""
    if 'user_listings' in filename:
        return get_all_user_listings()
    elif 'sales' in filename:
        return get_sales_data()
    elif 'active_deals' in filename:
        return get_all_active_deals()
    elif 'deal_confirmations' in filename:
        return get_all_deal_confirmations()
    elif 'auctions_data' in filename:
        return get_all_active_auctions()
    elif 'ended_auctions' in filename:
        return get_all_ended_auctions()
    elif 'giveaways_data' in filename:
        return get_all_active_giveaways()
    else:
        return {}

def save_json_data(filename, data):
    """Legacy function - now saves data to database"""
    # This function is now handled by individual database operations
    # We'll keep it for compatibility but it won't do anything
    pass

def add_user_listing_legacy(user_listings, user_id, message_id, car_name):
    """Legacy function - now uses database"""
    add_user_listing(user_id, message_id, car_name)

# Keep the old function name for compatibility
add_user_listing_original = add_user_listing_legacy

# Database-backed functions (replacing the old global variables)
def load_active_deals():
    """Load active deals from database"""
    # This is now handled automatically by the database functions
    pass

def save_active_deals():
    """Save active deals to database"""
    # This is now handled automatically by the database functions
    pass

def load_deal_confirmations():
    """Load deal confirmations from database"""
    # This is now handled automatically by the database functions
    pass

def save_deal_confirmations():
    """Save deal confirmations to database"""
    # This is now handled automatically by the database functions
    pass

# Initialize database when module is imported
try:
    init_database()
except Exception as e:
    print(f"Error initializing database in utils.py: {e}")
import discord
from discord import app_commands, Interaction
import asyncio
import os
from typing import Dict, List

# Import new configuration and logging
from config import config
from logger_config import get_logger, log_info, log_error, log_warning
from validation import SecurityValidator

# Import new security system
try:
    from security_system import SecurityMonitor, setup_security_monitoring
    from commands.admin_security import setup_admin_security_commands
    SECURITY_SYSTEM_AVAILABLE = True
except ImportError:
    SECURITY_SYSTEM_AVAILABLE = False
    log_warning("Security system not available - running without ingame ID monitoring")

# Import command modules
from commands.utils import (
    private_channels_activity, private_channel_messages, 
    send_security_notice, log_channel_messages
)
from database_mysql import (
    init_connection_pool, init_database, get_all_user_listings, get_user_listings, 
    remove_user_listing, add_user_listing, get_user_sales, get_active_deal,
    remove_active_deal, remove_deal_confirmation, record_sale,
    update_deal_confirmation, get_deal_confirmation, add_deal_confirmation,
    populate_car_listings, populate_car_shortcodes, close_support_ticket, 
    close_report_ticket
)
from commands.sell import (
    setup_sell_command, handle_sell_image_upload, handle_buy_button, handle_make_offer_button
)
from commands.trade import (
    setup_trade_command, handle_trade_image_upload, handle_trade_button, handle_make_trade_offer_button
)
from commands.auction import (
    setup_auction_commands, handle_auction_image_upload, handle_auction_bid,
    handle_auction_accept, handle_auction_reject, restore_active_auctions,
    setup_persistent_auction_confirmation_views
)
from commands.giveaway import (
    setup_giveaway_command, handle_giveaway_image_upload, handle_giveaway_join,
    restore_active_giveaways
)
from commands.report import setup_report_command
from commands.support import setup_support_command
from commands.ticket_embed import setup_ticket_embed, setup_persistent_views
from commands.auction_embed import setup_auction_embed, setup_persistent_auction_views
from commands.giveaway_embed import setup_giveaway_embed, setup_persistent_giveaway_views
from commands.sell_trade_embed import setup_sell_trade_embed, setup_persistent_sell_trade_views
from commands.rules_embed import setup_rules_embed, setup_persistent_rules_views
from commands.deal_confirmation import setup_persistent_deal_confirmation_views, DealConfirmationView

# Initialize logger
logger = get_logger("main")

# Validate configuration
try:
    config.validate()
    log_info("Configuration validated successfully")
except ValueError as e:
    log_error(f"Configuration error: {e}")
    exit(1)

# Define intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Create bot instance
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

async def check_inactive_channels():
    """Check for inactive private channels and close them after configured timeout"""
    while True:
        try:
            current_time = asyncio.get_event_loop().time()
            channels_to_close = []

            for channel_id, last_activity in list(private_channels_activity.items()):
                if current_time - last_activity > config.CHANNEL_INACTIVITY_TIMEOUT:
                    channels_to_close.append(channel_id)

            for channel_id in channels_to_close:
                try:
                    channel = bot.get_channel(channel_id)
                    if channel and (channel.name.startswith('car-sale-') or channel.name.startswith('car-trade-') or
                                   channel.name.startswith('report-') or channel.name.startswith('support-') or
                                   channel.name.startswith('auction-deal-') or channel.name.startswith('giveaway-claim-') or
                                   channel.name.startswith('admin-giveaway-claim-')):
                        # Send notice before closing
                        embed = discord.Embed(
                            title="⏰ Channel Auto-Close",
                            description=f"This channel has been inactive for {config.CHANNEL_INACTIVITY_TIMEOUT//3600} hours and will be automatically closed.",
                            color=discord.Color.orange()
                        )
                        await channel.send(embed=embed)
                        await asyncio.sleep(10)

                        # Log messages before closing
                        await log_channel_messages(bot, channel)
                        await channel.delete(reason="Auto-closed due to inactivity")
                        log_info(f"Auto-closed inactive channel: {channel.name}")

                    # Remove from tracking
                    if channel_id in private_channels_activity:
                        del private_channels_activity[channel_id]

                    # Clean up active deals and confirmations
                    remove_active_deal(channel_id)
                    remove_deal_confirmation(channel_id)

                except Exception as e:
                    log_error(f"Error auto-closing channel {channel_id}: {e}")
                    if channel_id in private_channels_activity:
                        del private_channels_activity[channel_id]

            # Clean up old message logs
            cutoff_time = current_time - 86400  # 24 hours
            channels_to_clean = []

            for channel_id in list(private_channel_messages.keys()):
                try:
                    channel = bot.get_channel(channel_id)
                    if not channel:
                        channels_to_clean.append(channel_id)
                except Exception:
                    channels_to_clean.append(channel_id)

            for channel_id in channels_to_clean:
                if channel_id in private_channel_messages:
                    del private_channel_messages[channel_id]

        except Exception as e:
            log_error(f"Error in check_inactive_channels: {e}")

        await asyncio.sleep(300)  # Check every 5 minutes

@bot.event
async def on_ready():
    log_info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    log_info('Bot is ready and online')

    try:
        # Clear existing commands first
        log_info("Clearing existing commands...")
        tree.clear_commands(guild=None)
        await asyncio.sleep(3)

        # Setup all commands
        log_info("Setting up commands...")
        from commands.sell import setup_sell_command
        from commands.trade import setup_trade_command
        from commands.auction import setup_auction_commands
        from commands.giveaway import setup_giveaway_command

        setup_sell_command(tree)
        log_info("  - Sell command setup")

        setup_trade_command(tree)
        log_info("  - Trade command setup")

        try:
            setup_auction_commands(tree)
            print("  - Auction commands setup")
        except Exception as e:
            print(f"  - Auction commands setup failed: {e}")
            print("  - Continuing without auction commands...")

        setup_giveaway_command(tree)
        print("  - Giveaway command setup")

        setup_report_command(tree)
        print("  - Report command setup")

        setup_support_command(tree)
        print("  - Support command setup")

        # Setup utility commands (includes close, delete, relist, etc.)
        setup_utility_commands(tree)
        print("  - Utility commands setup (including close)")

        # Setup admin security commands if available
        if SECURITY_SYSTEM_AVAILABLE:
            setup_admin_security_commands(tree)
            print("  - Admin security commands setup")

        # Force sync commands
        print("Syncing commands with Discord...")
        try:
            synced = await tree.sync()
            print(f'✅ Commands synced successfully! ({len(synced)} commands)')

            # Print synced command names for debugging
            command_names = [cmd.name for cmd in synced]
            print(f"  Synced commands: {', '.join(command_names)}")

            # Verify close command is included
            if 'close' in command_names:
                print("  ✅ Close command successfully registered")
            else:
                print("  ❌ Close command NOT found in synced commands")

        except discord.HTTPException as e:
            print(f'HTTPException during sync: {e}')
            if e.status == 429:  # Rate limited
                print("Rate limited. Waiting 60 seconds before retry...")
                await asyncio.sleep(60)
                synced = await tree.sync()
                print(f'Retry sync completed! ({len(synced)} commands)')
            else:
                raise
        except Exception as e:
            print(f'Failed to sync commands: {e}')
            print("Attempting recovery sync...")

            # Try a complete reset
            tree.clear_commands(guild=None)
            await asyncio.sleep(3)

            # Re-setup only essential commands
            setup_utility_commands(tree)  # This includes close
            setup_sell_command(tree)
            setup_trade_command(tree)

            try:
                synced = await tree.sync()
                print(f'Recovery sync completed! ({len(synced)} commands)')
                command_names = [cmd.name for cmd in synced]
                print(f"  Recovery commands: {', '.join(command_names)}")
            except Exception as e2:
                print(f'Recovery sync also failed: {e2}')
                print("Bot will continue but commands may not work properly")

    except Exception as e:
        print(f'Critical error in command setup: {e}')
        import traceback
        traceback.print_exc()

    # Initialize database
    try:
        # Check if MySQL environment variables are properly set
        mysql_host = os.environ.get('MYSQL_HOST')
        mysql_user = os.environ.get('MYSQL_USER')
        mysql_password = os.environ.get('MYSQL_PASSWORD')
        mysql_database = os.environ.get('MYSQL_DATABASE')

        if not mysql_password:
            print("❌ ERROR: MYSQL_PASSWORD environment variable not set!")
            print("Please set up MySQL database environment variables:")
            print("1. MYSQL_HOST (default: localhost)")
            print("2. MYSQL_USER (default: root)")
            print("3. MYSQL_PASSWORD (required)")
            print("4. MYSQL_DATABASE (default: bot_database)")
            print("5. MYSQL_PORT (default: 3306)")
            return

        init_connection_pool()
        init_database()
        print("MySQL database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        print("Please check your MySQL database setup and environment variables")
        return

    # Load car models for recognition
    populate_car_listings()
    populate_car_shortcodes()

    # Setup persistent views
    setup_persistent_views(bot)
    setup_persistent_channel_button_views(bot)

    # Import and setup persistent views for support and report
    from commands.support import setup_persistent_support_views, SupportChannelView, ensure_support_channel_buttons
    from commands.report import setup_persistent_report_views, ReportChannelView, ensure_report_channel_buttons

    # First add the view classes to ensure they persist across bot restarts
    bot.add_view(SupportChannelView(0))  # Channel ID 0 is a placeholder for persistent views
    bot.add_view(ReportChannelView(0))   # Channel ID 0 is a placeholder for persistent views
    
    setup_persistent_support_views(bot)
    setup_persistent_report_views(bot)
    
    # Ensure existing channels have close buttons
    await ensure_support_channel_buttons(bot)
    await ensure_report_channel_buttons(bot)
    setup_persistent_auction_views(bot)
    setup_persistent_giveaway_views(bot)
    setup_persistent_sell_trade_views(bot)
    setup_persistent_rules_views(bot)
    setup_persistent_deal_confirmation_views(bot)
    setup_persistent_auction_confirmation_views(bot)
    
    # Setup persistent offer views
    from commands.sell import setup_persistent_offer_views
    from commands.trade import setup_persistent_trade_offer_views
    setup_persistent_offer_views(bot)
    setup_persistent_trade_offer_views(bot)
    print("Persistent views setup complete")

    # Setup embeds
    await setup_ticket_embed(bot)
    print("Ticket embed setup complete")

    await setup_auction_embed(bot)
    print("Auction embed setup complete")

    await setup_giveaway_embed(bot)
    print("Giveaway embed setup complete")

    await setup_sell_trade_embed(bot)
    print("Sell/Trade embed setup complete")

    await setup_rules_embed(bot)
    print("Rules embed setup complete")

    # Restore active auctions and giveaways
    try:
        await restore_active_auctions(bot)
        await restore_active_giveaways(bot)
        print('Active auctions and giveaways restored')
    except Exception as e:
        print(f'Error restoring data: {e}')

    # Initialize security monitoring
    if SECURITY_SYSTEM_AVAILABLE:
        security_monitor = setup_security_monitoring()
        print('Security monitoring system initialized')

    # Start background task
    try:
        bot.loop.create_task(check_inactive_channels())
        print('Background task started')
    except Exception as e:
        print(f'Error starting background task: {e}')

    print('Bot initialization complete!')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Handle support channel
    if message.channel.id == config.SUPPORT_CHANNEL_ID:
        if not message.author.guild_permissions.administrator and not message.interaction:
            try:
                await message.delete()
                log_info(f"Deleted non-admin message from {message.author} in #support")
            except discord.HTTPException as e:
                log_error(f"Failed to delete message in #support: {e}")
        return

    # Update activity for private channels and monitor for risky content
    if (message.channel.name.startswith('car-sale-') or message.channel.name.startswith('car-trade-') or
        message.channel.name.startswith('report-') or message.channel.name.startswith('support-') or
        message.channel.name.startswith('auction-deal-') or message.channel.name.startswith('giveaway-claim-') or
        message.channel.name.startswith('admin-giveaway-claim-')):
        private_channels_activity[message.channel.id] = asyncio.get_event_loop().time()

        # Check for risky content in trade channels and giveaway claim rooms
        if (message.channel.name.startswith('car-sale-') or message.channel.name.startswith('car-trade-') or
            message.channel.name.startswith('auction-deal-') or message.channel.name.startswith('giveaway-claim-') or
            message.channel.name.startswith('admin-giveaway-claim-')):
            
            # NEW SECURITY SYSTEM: Check for ingame ID mismatches
            security_warning_sent = False
            if SECURITY_SYSTEM_AVAILABLE:
                try:
                    security_warning_sent = await SecurityMonitor.check_message_for_id_mismatch(message)
                except Exception as e:
                    log_error(f"Error in security ID check: {e}", exc_info=True)
            
            # Original risky content detection
            dm_flags, payment_flags = SecurityValidator.check_risky_content(message.content)

            if dm_flags or payment_flags:
                warning_embed = discord.Embed(
                    title="⚠️ Warning",
                    description="All trades must stay inside this channel. Using real money or private messages is not allowed and may result in punishment.",
                    color=discord.Color.red()
                )
                try:
                    await message.channel.send(embed=warning_embed)
                except discord.HTTPException:
                    pass

            # Store message for logging
            if message.channel.id not in private_channel_messages:
                private_channel_messages[message.channel.id] = []

            private_channel_messages[message.channel.id].append({
                'message': message,
                'flagged': bool(dm_flags or payment_flags or security_warning_sent),
                'dm_flags': dm_flags,
                'payment_flags': payment_flags,
                'security_flagged': security_warning_sent
            })
        else:
            # Store normal messages for logging
            if message.channel.id not in private_channel_messages:
                private_channel_messages[message.channel.id] = []

            private_channel_messages[message.channel.id].append({
                'message': message,
                'flagged': False,
                'dm_flags': [],
                'payment_flags': []
            })

    # Handle auction bidding in auction forum threads
    if (hasattr(message.channel, 'parent') and 
        message.channel.parent and 
        message.channel.parent.id == AUCTION_FORUM_ID and
        not message.author.guild_permissions.administrator):
        await handle_auction_bid(bot, message)
        return

    # Handle image uploads for listings
    if message.channel.id in [SELL_CHANNEL_ID, TRADE_CHANNEL_ID, AUCTION_CHANNEL_ID, GIVEAWAY_CHANNEL_ID, SELL_TRADE_CHANNEL_ID]:
        user_id = message.author.id
        handled = False

        # Try each listing type - only try one handler per channel to avoid duplicates
        if message.channel.id in [SELL_CHANNEL_ID, SELL_TRADE_CHANNEL_ID]:
            # Try sell first, then trade for the sell/trade channel
            handled = await handle_sell_image_upload(bot, message)
            if not handled and message.channel.id == SELL_TRADE_CHANNEL_ID:
                handled = await handle_trade_image_upload(bot, message)
        elif message.channel.id == TRADE_CHANNEL_ID:
            handled = await handle_trade_image_upload(bot, message)
        elif message.channel.id == AUCTION_CHANNEL_ID:
            # Only try auction handler once
            handled = await handle_auction_image_upload(bot, message)
        elif message.channel.id == GIVEAWAY_CHANNEL_ID:
            handled = await handle_giveaway_image_upload(bot, message)

        # Generic deletion for non-admin messages that weren't handled
        if not handled and not message.author.guild_permissions.administrator:
            try:
                await message.delete()
                print(f"Deleted non-bot message from {message.author} in #{message.channel.name}")
            except discord.HTTPException as e:
                print(f"Failed to delete message: {e}")

@bot.event
async def on_interaction(interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data['custom_id']

    # Handle button interactions
    if custom_id.startswith('buy_car_'):
        await handle_buy_button(bot, interaction)
    elif custom_id.startswith('trade_car_'):
        await handle_trade_button(bot, interaction)
    elif custom_id.startswith('make_offer_'):
        await handle_make_offer_button(bot, interaction)
    elif custom_id.startswith('make_trade_offer_'):
        await handle_make_trade_offer_button(bot, interaction)
    # Giveaway interactions are now handled by JoinGiveawayView class
    elif custom_id.startswith('accept_auction_'):
        auction_id = custom_id.split('_')[2]
        await handle_auction_accept(bot, interaction, auction_id)
    elif custom_id.startswith('reject_auction_'):
        auction_id = custom_id.split('_')[2]
        await handle_auction_reject(bot, interaction, auction_id)
    elif custom_id.startswith('confirm_deal_'):
        # Handle deal confirmation buttons (already handled in close command)
        pass

async def handle_delete_command(interaction: discord.Interaction):
    """Handle delete command logic for both slash command and button"""
    user_id = interaction.user.id

    if interaction.channel_id not in [SELL_CHANNEL_ID, TRADE_CHANNEL_ID, SELL_TRADE_CHANNEL_ID]:
        await interaction.response.send_message(
            "This command can only be used in the #sell-cars, #trade-cars, or #make-sell-trade channels.",
            ephemeral=True
        )
        return

    # Get fresh listings
    user_listings = get_user_listings(user_id)
    if not user_listings:
        await interaction.response.send_message(
            "You don't have any active listings to delete.",
            ephemeral=True
        )
        return

    # Create dropdown options
    options = []
    for listing in user_listings:
        options.append(discord.SelectOption(
            label=listing['car_name'],
            value=str(listing['message_id'])
        ))

    if not options:
        await interaction.response.send_message(
            "You don't have any active listings to delete.",
            ephemeral=True
        )
        return

    async def delete_callback(select_interaction):
        selected_message_id = int(select.values[0])

        # Get fresh listings to find the selected one
        current_listings = get_user_listings(user_id)
        selected_car_name = None

        for listing in current_listings:
            if listing['message_id'] == selected_message_id:
                selected_car_name = listing['car_name']
                break

        if not selected_car_name:
            await select_interaction.response.send_message(
                "This listing no longer exists.",
                ephemeral=True
            )
            return

        try:
            # Try to find the message in the current channel first
            message = None
            try:
                message = await interaction.channel.fetch_message(selected_message_id)
            except discord.NotFound:
                # If not found in current channel, try the other channels
                for channel_id in [SELL_CHANNEL_ID, TRADE_CHANNEL_ID]:
                    if channel_id != interaction.channel_id:
                        other_channel = interaction.guild.get_channel(channel_id)
                        if other_channel:
                            try:
                                message = await other_channel.fetch_message(selected_message_id)
                                break
                            except discord.NotFound:
                                continue

            if message:
                await message.delete()

            # Remove from database
            remove_user_listing(user_id, selected_message_id)

            await select_interaction.response.send_message(
                f"Your listing for **{selected_car_name}** has been deleted successfully!",
                ephemeral=True
            )

        except discord.NotFound:
            # Message not found, but still remove from database
            remove_user_listing(user_id, selected_message_id)
            await select_interaction.response.send_message(
                "Your listing was already deleted or not found, but has been removed from your active listings.",
                ephemeral=True
            )
        except Exception as e:
            await select_interaction.response.send_message(
                f"An error occurred: {str(e)}",
                ephemeral=True
            )

    select = discord.ui.Select(
        placeholder="Select the car listing to delete...",
        options=options
    )
    view = discord.ui.View()
    select.callback = delete_callback
    view.add_item(select)

    await interaction.response.send_message(view=view, ephemeral=True)

async def handle_relist_command(interaction: discord.Interaction):
    """Handle relist command logic for both slash command and button"""
    user_id = interaction.user.id

    # Check if we're in the correct channel
    if interaction.channel_id not in [SELL_CHANNEL_ID, TRADE_CHANNEL_ID, SELL_TRADE_CHANNEL_ID]:
        await interaction.response.send_message(
            "This command can only be used in the #sell-cars, #trade-cars, or #make-sell-trade channels.",
            ephemeral=True
        )
        return

    # Get fresh listings from database
    user_listings = get_user_listings(user_id)
    if not user_listings:
        await interaction.response.send_message(
            "You don't have any active listings to relist.",
            ephemeral=True
        )
        return

    # Create dropdown options
    options = []
    for listing in user_listings:
        # Add listing type indicator to the label
        listing_type = listing.get('listing_type', 'sell')
        type_icon = '🚗' if listing_type == 'sell' else '🔄'
        options.append(discord.SelectOption(
            label=f"{type_icon} {listing['car_name']} ({listing_type})",
            value=str(listing['message_id'])
        ))

    if not options:
        await interaction.response.send_message(
            "You don't have any active listings to relist.",
            ephemeral=True
        )
        return

    # Create a select menu with the user's listings
    async def relist_callback(select_interaction):
        selected_message_id = int(select.values[0])

        # Get fresh listings to find the selected one
        current_listings = get_user_listings(user_id)
        selected_listing = None

        for listing in current_listings:
            if listing['message_id'] == selected_message_id:
                selected_listing = listing
                break

        if not selected_listing:
            await select_interaction.response.send_message(
                "This listing no longer exists.",
                ephemeral=True
            )
            return

        original_message = None
        original_channel = None

        try:
            # Try to find the message in both channels
            sell_channel = interaction.guild.get_channel(SELL_CHANNEL_ID)
            trade_channel = interaction.guild.get_channel(TRADE_CHANNEL_ID)

            # First try current channel
            try:
                original_message = await interaction.channel.fetch_message(selected_message_id)
                original_channel = interaction.channel
            except discord.NotFound:
                # Try the other channels
                for channel in [sell_channel, trade_channel]:
                    if channel and channel.id != interaction.channel_id:
                        try:
                            original_message = await channel.fetch_message(selected_message_id)
                            original_channel = channel
                            break
                        except discord.NotFound:
                            continue

            if not original_message:
                # Message not found anywhere, remove from database
                remove_user_listing(user_id, selected_message_id)
                await select_interaction.response.send_message(
                    "Your original listing was not found and has been removed from your active listings.",
                    ephemeral=True
                )
                return

            if not original_message.embeds:
                await select_interaction.response.send_message(
                    "Could not find listing data to relist.",
                    ephemeral=True
                )
                return

            embed = original_message.embeds[0]
            car_name = embed.title.replace('🚗 **', '').replace('🔄 **', '').replace('**', '').strip()
            image_url = embed.image.url if embed.image else None
            description = embed.description

            # Determine the original listing type and target channel
            original_listing_type = selected_listing.get('listing_type', 'sell')

            # Determine target channel based on original listing type
            if original_listing_type == 'sell':
                target_channel = interaction.guild.get_channel(SELL_CHANNEL_ID)
                new_embed = discord.Embed(
                    title=f'🚗 **{car_name.upper()}**',
                    description=description,
                    color=discord.Color.green()
                )
                if image_url:
                    new_embed.set_image(url=image_url)
                new_embed.set_footer(text=f'Listed by {interaction.user.display_name}', icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
                new_embed.timestamp = discord.utils.utcnow()

                # Create view with buy button
                view = discord.ui.View()
                buy_button = discord.ui.Button(label='Buy Car', style=discord.ButtonStyle.green, custom_id=f'buy_car_{user_id}')
                view.add_item(buy_button)
                new_listing_type = 'sell'

            elif original_listing_type == 'trade':
                target_channel = interaction.guild.get_channel(TRADE_CHANNEL_ID)
                new_embed = discord.Embed(
                    title=f'🔄 **{car_name.upper()}**',
                    description=description,
                    color=discord.Color.blue()
                )
                if image_url:
                    new_embed.set_image(url=image_url)
                new_embed.set_footer(text=f'Listed by {interaction.user.display_name}', icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
                new_embed.timestamp = discord.utils.utcnow()

                # Create view with trade button
                view = discord.ui.View()
                trade_button = discord.ui.Button(label='Trade Car', style=discord.ButtonStyle.primary, custom_id=f'trade_car_{user_id}')
                view.add_item(trade_button)
                new_listing_type = 'trade'

            # Send new listing in the appropriate channel
            new_listing = await target_channel.send(embed=new_embed, view=view)

            # Delete original listing
            try:
                await original_message.delete()
            except discord.HTTPException as e:
                print(f"Could not delete original message: {e}")

            # Update database: remove old listing and add new one
            remove_user_listing(user_id, selected_message_id)
            add_user_listing(user_id, new_listing.id, car_name, new_listing_type)

            await select_interaction.response.send_message(
                f"Your listing for **{car_name}** has been relisted successfully in #{target_channel.name}!",
                ephemeral=True
            )

        except Exception as e:
            print(f"Error in relist: {e}")
            await select_interaction.response.send_message(
                f"An error occurred while relisting: {str(e)}",
                ephemeral=True
            )

    select = discord.ui.Select(
        placeholder="Select the car listing to relist...",
        options=options
    )
    view = discord.ui.View()
    select.callback = relist_callback
    view.add_item(select)

    await interaction.response.send_message(view=view, ephemeral=True)

async def handle_cancel_command(interaction: discord.Interaction):
    """Handle cancel command logic for deal private channels"""
    channel_id = interaction.channel_id
    channel = interaction.channel

    # Check if it's a deal channel (sell, trade, auction, or giveaway claim)
    if not (channel.name.startswith('car-sale-') or 
            channel.name.startswith('car-trade-') or 
            channel.name.startswith('auction-deal-') or
            channel.name.startswith('giveaway-claim-') or
            channel.name.startswith('admin-giveaway-claim-')):
        await interaction.response.send_message(
            "This command can only be used in deal channels (car-sale-, car-trade-, auction-deal-, giveaway-claim-).",
            ephemeral=True
        )
        return

    # Get deal information from database
    try:
        deal_info = get_active_deal(channel_id)
    except Exception as e:
        print(f"Error getting deal info: {e}")
        deal_info = None

    # Determine channel type for messaging
    channel_type = "Deal"
    if channel.name.startswith('car-sale-'):
        channel_type = "Sale"
    elif channel.name.startswith('car-trade-'):
        channel_type = "Trade"
    elif channel.name.startswith('auction-deal-'):
        channel_type = "Auction Deal"
    elif channel.name.startswith('giveaway-claim-') or channel.name.startswith('admin-giveaway-claim-'):
        channel_type = "Giveaway Claim"

    embed = discord.Embed(
        title="❌ Deal Cancelled",
        description=f"This {channel_type.lower()} has been cancelled by {interaction.user.mention}.\n\n⏳ This channel will be deleted in 10 seconds.",
        color=discord.Color.red()
    )

    # Add deal info if available
    if deal_info:
        car_name = deal_info.get("car_name", "Unknown")
        embed.add_field(name="Deal Details", value=f"**Item:** {car_name}", inline=False)

    # Respond immediately to avoid timeout
    try:
        await interaction.response.send_message(embed=embed)
    except discord.errors.NotFound:
        # Interaction already expired, send as regular message
        await channel.send(embed=embed)
    except Exception as e:
        print(f"Error responding to cancel interaction: {e}")
        await channel.send(embed=embed)

    # Log messages before closing
    await log_channel_messages(bot, channel)

    # Clean up database and tracking
    if channel_id in private_channels_activity:
        del private_channels_activity[channel_id]

    try:
        remove_active_deal(channel_id)
        remove_deal_confirmation(channel_id)
    except Exception as e:
        print(f"Error cleaning up deal data: {e}")

    # Schedule channel deletion
    async def delayed_deletion():
        await asyncio.sleep(10)
        try:
            await channel.delete(reason=f"{channel_type} cancelled by user")
            print(f"Deleted cancelled {channel_type.lower()} channel: {channel.name}")
        except Exception as e:
            print(f"Error deleting cancelled channel: {e}")

    asyncio.create_task(delayed_deletion())

async def handle_close_command(interaction: discord.Interaction):
    """Handle close command logic for both slash command and button"""
    channel_id = interaction.channel_id
    channel = interaction.channel

    # Check if it's a support or report channel
    if channel.name.startswith('support-') or channel.name.startswith('report-'):
        channel_type = "support" if channel.name.startswith('support-') else "report"

        embed = discord.Embed(
            title=f"🔒 Closing {channel_type.title()} Channel",
            description=f"This {channel_type} channel will be closed in 10 seconds.",
            color=discord.Color.orange()
        )

        # Respond immediately to avoid timeout
        try:
            await interaction.response.send_message(embed=embed)
        except discord.errors.NotFound:
            # Interaction already expired, send as regular message
            await channel.send(embed=embed)
        except Exception as e:
            print(f"Error responding to close interaction: {e}")
            return

        await asyncio.sleep(10)
        await log_channel_messages(bot, channel)

        # Close ticket in database
        try:
            if channel_type == "support":
                close_support_ticket(channel_id)
            else:
                close_report_ticket(channel_id)
        except Exception as e:
            print(f"Error closing ticket in database: {e}")

        if channel_id in private_channels_activity:
            del private_channels_activity[channel_id]

        try:
            await channel.delete(reason=f"{channel_type.title()} channel closed by user")
        except Exception as e:
            print(f"Error closing {channel_type} channel: {e}")
        return

    # Check if it's a deal channel (sell, trade, auction, or giveaway claim)
    elif (channel.name.startswith('car-sale-') or 
              channel.name.startswith('car-trade-') or 
              channel.name.startswith('auction-deal-') or
              channel.name.startswith('giveaway-claim-') or
              channel.name.startswith('admin-giveaway-claim-')):

        # Check if there's already an active confirmation process for this channel
        existing_confirmations = get_deal_confirmation(channel_id)
        if existing_confirmations:
            await interaction.response.send_message(
                "A deal confirmation is already in progress for this channel. Please use the existing confirmation buttons.",
                ephemeral=True
            )
            return

        # Determine if this is a giveaway claim room
        is_giveaway_claim = channel.name.startswith('giveaway-claim-') or channel.name.startswith('admin-giveaway-claim-')

        # Get deal information from database
        try:
            deal_info = get_active_deal(channel_id)
        except Exception as e:
            print(f"Error getting deal info: {e}")
            deal_info = None

        if not deal_info:
            if is_giveaway_claim:
                # For giveaway claim rooms, provide a manual confirmation option
                embed = discord.Embed(
                    title="🎁 Close Giveaway Claim Room",
                    description=f"No deal data found for this giveaway claim room.\n\n"
                               f"**Channel:** {channel.name}\n\n"
                               f"Click the button below to confirm the prize was delivered and close this room.",
                    color=discord.Color.purple()
                )

                # Create a manual confirmation button
                view = discord.ui.View(timeout=300)
                confirm_button = discord.ui.Button(
                    label='✅ Confirm Prize Delivered',
                    style=discord.ButtonStyle.green,
                    custom_id=f'manual_confirm_{channel_id}'
                )

                async def manual_confirm_callback(button_interaction):
                    completion_embed = discord.Embed(
                        title="🎁 Prize Delivery Confirmed!",
                        description=f"Prize delivery has been manually confirmed.\n\n⏳ This channel will be deleted in 10 seconds.",
                        color=discord.Color.purple()
                    )

                    try:
                        await button_interaction.response.edit_message(embed=completion_embed, view=None)
                    except discord.errors.NotFound:
                        await channel.send(embed=completion_embed)

                    # Clean up and schedule deletion
                    if channel_id in private_channels_activity:
                        del private_channels_activity[channel_id]
                    try:
                        remove_deal_confirmation(channel_id)
                    except Exception as e:
                        print(f"Error removing deal confirmation: {e}")

                    async def delayed_deletion():
                        await asyncio.sleep(10)
                        try:
                            await log_channel_messages(bot, channel)
                            await channel.delete(reason="Giveaway claim room closed - prize delivery confirmed")
                            print(f"Deleted giveaway claim channel: {channel.name}")
                        except Exception as e:
                            print(f"Error deleting giveaway claim channel: {e}")

                    asyncio.create_task(delayed_deletion())

                confirm_button.callback = manual_confirm_callback
                view.add_item(confirm_button)

                try:
                    await interaction.response.send_message(embed=embed, view=view)
                except discord.errors.NotFound:
                    await channel.send(embed=embed, view=view)
                return
            else:
                # For regular deal channels, show the normal missing data message
                embed = discord.Embed(
                    title="⚠️ Deal Data Missing",
                    description=f"No active deal data found for this channel. This may happen after a bot restart.\n\n"
                               f"**Channel:** {channel.name}\n"
                               f"**Action:** This channel will be closed in 30 seconds.\n\n"
                               f"If this was an active deal, please contact an administrator.",
                    color=discord.Color.orange()
                )
                await interaction.response.send_message(embed=embed)

                await asyncio.sleep(30)

                # Log messages before closing
                await log_channel_messages(bot, channel)

                if channel_id in private_channels_activity:
                    del private_channels_activity[channel_id]
                remove_deal_confirmation(channel_id)

                try:
                    await channel.delete(reason="Deal channel closed - no dealata found")
                except Exception as e:
                    print(f"Error closing deal channel: {e}")
                return

        seller_id = deal_info["seller_id"]
        buyer_id = deal_info["buyer_id"]
        car_name = deal_info.get("car_name", "Unknown Car")

        # Determine if this is a giveaway claim room
        is_giveaway_claim = channel.name.startswith('giveaway-claim-') or channel.name.startswith('admin-giveaway-claim-')

        # Adjust labels for giveaway claims
        if is_giveaway_claim:
            seller_label = "Host"
            buyer_label = "Winner"
            deal_type = "Giveaway Prize"
        else:
            seller_label = "Seller"
            buyer_label = "Buyer"
            deal_type = "Car"

        # Fetch user objects
        try:
            seller = await bot.fetch_user(seller_id)
            buyer = await bot.fetch_user(buyer_id)
        except discord.NotFound:
            await interaction.response.send_message(
                f"Error: Could not find {seller_label.lower()} or {buyer_label.lower()} information.",
                ephemeral=True
            )
            return

        # Initialize confirmation tracking if it doesn't exist
        try:
            confirmations = get_deal_confirmation(channel_id)
            if not confirmations:
                add_deal_confirmation(channel_id)
                confirmations = {"buyer_confirmed": False, "seller_confirmed": False}
        except Exception as e:
            print(f"Error handling deal confirmations: {e}")
            confirmations = {"buyer_confirmed": False, "seller_confirmed": False}

        # Create the confirmation embed
        embed = discord.Embed(
            title="🤝 Confirm Deal" if not is_giveaway_claim else "🎁 Confirm Prize Delivery",
            description=f"**{deal_type}:** {car_name}\n**{seller_label}:** {seller.mention}\n**{buyer_label}:** {buyer.mention}\n\nBoth parties need to confirm this {'deal' if not is_giveaway_claim else 'prize delivery'} was completed successfully.",
            color=discord.Color.blue() if not is_giveaway_claim else discord.Color.purple()
        )

        # Add confirmation status
        confirmation_status = ""
        if confirmations["buyer_confirmed"]:
            confirmation_status += f"✅ {buyer.mention} confirmed\n"
        else:
            confirmation_status += f"⏳ {buyer.mention} pending\n"

        if confirmations["seller_confirmed"]:
            confirmation_status += f"✅ {seller.mention} confirmed\n"
        else:
            confirmation_status += f"⏳ {seller.mention} pending\n"

        embed.add_field(name="Confirmation Status", value=confirmation_status, inline=False)

        # Create the persistent confirmation view
        view = DealConfirmationView(
            channel_id=channel_id,
            seller_id=seller_id,
            buyer_id=buyer_id,
            car_name=car_name,
            is_giveaway_claim=is_giveaway_claim
        )

        # Send the confirmation message
        try:
            await interaction.response.send_message(embed=embed, view=view)
        except discord.errors.NotFound:
            # Interaction expired, send as regular message
            await channel.send(embed=embed, view=view)
        except Exception as e:
            print(f"Error sending confirmation message: {e}")
            await channel.send(embed=embed, view=view)

    else:
        await interaction.response.send_message(
            "This command can only be used in deal channels (car-sale-, car-trade-, auction-deal-, giveaway-claim-) or support/report channels.",
            ephemeral=True
        )

def setup_utility_commands(tree):
    """Setup utility commands like /delete, /relist, /close, /clean, /cleanbot"""

    @tree.command(name="delete", description="Delete your car listing.")
    async def delete_listing_command(interaction: discord.Interaction):
        await handle_delete_command(interaction)

    @tree.command(name="relist", description="Move one of your active listings between sell and trade channels.")
    async def relist_command(interaction: discord.Interaction):
        await handle_relist_command(interaction)

    @tree.command(name="close", description="Close a deal, support ticket, or report.")
    async def close_command(interaction: discord.Interaction):
        await handle_close_command(interaction)

    @tree.command(name="progress", description="Check your trader role progress.")
    @app_commands.default_permissions(send_messages=True)
    async def progress_command(interaction: discord.Interaction):
        try:
            from database_mysql import get_user_sales
            from commands.trader_roles import format_trader_progress, get_user_trader_role_info

            user_sales = get_user_sales(interaction.user.id)
            role_info = await get_user_trader_role_info(bot, interaction.user.id)
            progress = format_trader_progress(user_sales)

            embed = discord.Embed(
                title="🏆 Your Trader Progress",
                description=f"**Deals Completed:** {user_sales}\n\n{progress}",
                color=discord.Color.blue()
            )

            if role_info:
                embed.add_field(
                    name="Current Role",
                    value=f"{role_info['discord_role'].mention}",
                    inline=True
                )

            embed.set_footer(text="Complete more deals to unlock higher trader ranks!")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"Error checking your progress: {str(e)}", ephemeral=True)



    @tree.command(name="clean", description="Clean up all messages in this channel (Admin only).")
    @app_commands.default_permissions(administrator=True)
    async def clean_command(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "This command is only available to administrators.",
                ephemeral=True
            )
            return

        await interaction.response.send_message("Cleaning all messages in this channel...", ephemeral=True)

        try:
            deleted_count = 0
            async for message in interaction.channel.history(limit=None):
                try:
                    await message.delete()
                    deleted_count += 1
                    await asyncio.sleep(0.5)  # Rate limit protection
                except Exception as e:
                    print(f"Failed to delete message: {e}")

            await interaction.edit_original_response(content=f"Deleted {deleted_count} messages from this channel.")
        except Exception as e:
            await interaction.edit_original_response(content=f"Error cleaning messages: {e}")

    @tree.command(name="cleanbot", description="Clean up all bot messages in this channel (Admin only).")
    @app_commands.default_permissions(administrator=True)
    async def cleanbot_command(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "This command is only available to administrators.",
                ephemeral=True
            )
            return

        await interaction.response.send_message("Cleaning bot messages...", ephemeral=True)

        try:
            deleted_count = 0
            async for message in interaction.channel.history(limit=None):
                if message.author == bot.user:
                    try:
                        await message.delete()
                        deleted_count += 1
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        print(f"Failed to delete message: {e}")

            await interaction.edit_original_response(content=f"Deleted {deleted_count} bot messages.")
        except Exception as e:
            await interaction.edit_original_response(content=f"Error cleaning messages: {e}")

    @tree.command(name="cancel", description="Cancel the current deal and close this private channel.")
    async def cancel_command(interaction: discord.Interaction):
        await handle_cancel_command(interaction)

    @tree.command(name="showcars", description="Display all recognized cars and their short codes (Admin only).")
    @app_commands.default_permissions(administrator=True)
    async def showcars_command(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "This command is only available to administrators.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Get all car listings from database
            from database_mysql import get_all_car_listings
            car_listings = get_all_car_listings()

            if not car_listings:
                await interaction.followup.send("No car listings found in the database.", ephemeral=True)
                return

            # Format the car listings
            formatted_cars = []
            for car in car_listings:
                car_name = car['car_name']
                short_codes = car.get('short_codes', '') or ''

                if short_codes and short_codes.strip():
                    formatted_cars.append(f"**{car_name}** — Short codes: {short_codes}")
                else:
                    formatted_cars.append(f"**{car_name}** — Short codes: None")

            # Paginate the results to avoid Discord's 2000 character limit
            message_parts = []
            current_message = f"**🚗 Recognized Cars ({len(car_listings)} total):**\n\n"

            for car_entry in formatted_cars:
                # Check if adding this car would exceed the limit
                if len(current_message + car_entry + "\n") > 1900:  # Leave some buffer
                    message_parts.append(current_message)
                    current_message = car_entry + "\n"
                else:
                    current_message += car_entry + "\n"

            # Add the remaining content
            if current_message.strip():
                message_parts.append(current_message)

            # Send the first message
            if message_parts:
                await interaction.followup.send(message_parts[0], ephemeral=True)

                # Send additional messages if needed
                for i, part in enumerate(message_parts[1:], 2):
                    await interaction.followup.send(f"**Page {i}:**\n\n{part}", ephemeral=True)
                    await asyncio.sleep(0.5)  # Small delay between messages

        except Exception as e:
            await interaction.followup.send(f"Error retrieving car listings: {str(e)}", ephemeral=True)

    @tree.command(name="checkrole", description="Check a user's trader role and progress (Admin only).")
    @app_commands.default_permissions(administrator=True)
    async def checkrole_command(interaction: discord.Interaction, user: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "This command is only available to administrators.",
                ephemeral=True
            )
            return

        try:
            from database_mysql import get_user_sales
            from commands.trader_roles import format_trader_progress, get_user_trader_role_info

            user_sales = get_user_sales(user.id)
            role_info = await get_user_trader_role_info(bot, user.id)
            progress = format_trader_progress(user_sales)

            embed = discord.Embed(
                title=f"🏆 Trader Role Status: {user.display_name}",
                description=f"**User:** {user.mention}\n**Deals Completed:** {user_sales}\n\n{progress}",
                color=discord.Color.blue()
            )

            if role_info:
                embed.add_field(
                    name="Current Discord Role",
                    value=f"{role_info['discord_role'].mention} (Threshold: {role_info['threshold']} deals)",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"Error checking user role: {str(e)}", ephemeral=True)

    @tree.command(name="updaterole", description="Force update a user's trader role (Admin only).")
    @app_commands.default_permissions(administrator=True)
    async def updaterole_command(interaction: discord.Interaction, user: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "This command is only available to administrators.",
                ephemeral=True
            )
            return

        try:
            from database_mysql import get_user_sales
            from commands.trader_roles import update_trader_role

            user_sales = get_user_sales(user.id)
            success, message = await update_trader_role(bot, user.id, user_sales)

            embed = discord.Embed(
                title="🔄 Role Update Result",
                description=f"**User:** {user.mention}\n**Deal Count:** {user_sales}\n**Result:** {message}",
                color=discord.Color.green() if success else discord.Color.red()
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"Error updating user role: {str(e)}", ephemeral=True)

    @tree.command(name="roleinfo", description="Display trader role system information (Admin only).")
    @app_commands.default_permissions(administrator=True)
    async def roleinfo_command(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "This command is only available to administrators.",
                ephemeral=True
            )
            return

        try:
            from commands.trader_roles import TRADER_ROLES

            embed = discord.Embed(
                title="🏆 Trader Role System",
                description="Automatic role assignment based on confirmed deal count:",
                color=discord.Color.gold()
            )

            role_text = ""
            for role in sorted(TRADER_ROLES, key=lambda x: x["threshold"]):
                discord_role = interaction.guild.get_role(role["role_id"])
                role_name = discord_role.name if discord_role else f"Role ID: {role['role_id']}"
                role_text += f"**{role['name']}** - {role['threshold']}+ deals - {role_name}\n"

            embed.add_field(name="Role Tiers", value=role_text, inline=False)
            embed.add_field(
                name="System Features",
                value="• Automatic assignment on deal completion\n• Removes previous roles when upgrading\n• Error handling for missing permissions\n• Both seller and buyer get credit for deals",
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"Error displaying role info: {str(e)}", ephemeral=True)

# Persistent View Class for Support/Report Channel Button
class CloseButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Disable timeout for persistent views

        close_button = discord.ui.Button(
            label="Close Channel",
            style=discord.ButtonStyle.danger,
            custom_id="close_support_report_channel"
        )

        close_button.callback = self.close_button_callback
        self.add_item(close_button)

    async def close_button_callback(self, interaction: discord.Interaction):
        await handle_close_command(interaction)

# Persistent View Class for Deal Channel Buttons
class DealButtonsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Disable timeout for persistent views

        complete_button = discord.ui.Button(
            label="Complete Deal",
            style=discord.ButtonStyle.success,
            custom_id="complete_deal_button"
        )

        cancel_button = discord.ui.Button(
            label="Cancel Deal",
            style=discord.ButtonStyle.danger,
            custom_id="cancel_deal_button"
        )

        complete_button.callback = self.complete_button_callback
        cancel_button.callback = self.cancel_button_callback

        self.add_item(complete_button)
        self.add_item(cancel_button)

    async def complete_button_callback(self, interaction: discord.Interaction):
        await handle_close_command(interaction)  # Using close command logic for deal completion

    async def cancel_button_callback(self, interaction: discord.Interaction):
        await handle_cancel_command(interaction)  # Using cancel command logic

def setup_persistent_channel_button_views(bot):
    """Setup persistent views for channel-specific buttons."""
    bot.add_view(CloseButtonView())
    bot.add_view(DealButtonsView())

if __name__ == "__main__":
    try:
        bot.run(config.BOT_TOKEN)
    except Exception as e:
        log_error(f"Failed to start bot: {e}", exc_info=True)
        exit(1)
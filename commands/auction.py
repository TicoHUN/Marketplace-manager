import discord
from discord.ui import Modal, TextInput, View, Button
from discord import app_commands, Interaction, TextStyle, ButtonStyle
import asyncio
import uuid
import random
from datetime import datetime, timedelta
from .utils import (
    listing_timeout, save_image_to_bot_channel, send_security_notice,
    private_channels_activity
)
from database_mysql import (
    add_pending_listing, remove_pending_listing, get_pending_listing,
    add_active_auction, get_active_auction, get_all_active_auctions,
    update_auction_bid, update_auction_status, remove_active_auction,
    add_ended_auction, get_all_ended_auctions, add_active_deal,
    record_sale, resolve_car_shortcode
)
from .car_disambiguation import handle_car_disambiguation

# Channel IDs
AUCTION_CHANNEL_ID = config.AUCTION_CHANNEL_ID  # ID for #make-auction channel
AUCTION_FORUM_ID = config.AUCTION_FORUM_ID  # ID for #auction-house forum channel

class AuctionConfirmationView(discord.ui.View):
    """Persistent view for auction accept/reject buttons"""
    
    def __init__(self, auction_id: str):
        super().__init__(timeout=None)  # Persistent view
        self.auction_id = auction_id

        # Accept button
        accept_button = discord.ui.Button(
            label='✅ Accept Price',
            style=discord.ButtonStyle.green,
            custom_id=f'accept_auction_{auction_id}'
        )
        accept_button.callback = self.accept_callback
        self.add_item(accept_button)

        # Reject button
        reject_button = discord.ui.Button(
            label='❌ Reject Price',
            style=discord.ButtonStyle.red,
            custom_id=f'reject_auction_{auction_id}'
        )
        reject_button.callback = self.reject_callback
        self.add_item(reject_button)

    async def accept_callback(self, interaction):
        """Handle accept button click"""
        from database_mysql import get_active_auction
        
        auction = get_active_auction(self.auction_id)
        if not auction:
            await interaction.response.send_message(
                "This auction is no longer active.",
                ephemeral=True
            )
            return

        if interaction.user.id != auction['seller_id']:
            await interaction.response.send_message(
                "Only the seller can accept or reject this auction.",
                ephemeral=True
            )
            return

        # Disable the view immediately to prevent double-clicks
        for item in self.children:
            item.disabled = True

        # Respond to the button interaction first
        await interaction.response.edit_message(view=self)

        # Handle the auction accept logic
        from main import bot
        await handle_auction_accept(bot, interaction, self.auction_id)

    async def reject_callback(self, interaction):
        """Handle reject button click"""
        from database_mysql import get_active_auction
        
        auction = get_active_auction(self.auction_id)
        if not auction:
            await interaction.response.send_message(
                "This auction is no longer active.",
                ephemeral=True
            )
            return

        if interaction.user.id != auction['seller_id']:
            await interaction.response.send_message(
                "Only the seller can accept or reject this auction.",
                ephemeral=True
            )
            return

        # Disable the view immediately to prevent double-clicks
        for item in self.children:
            item.disabled = True

        # Respond to the button interaction first
        await interaction.response.edit_message(view=self)

        # Handle the auction reject logic
        from main import bot
        await handle_auction_reject(bot, interaction, self.auction_id)

class AuctionDealChannelView(discord.ui.View):
    """View for auction deal channel buttons"""
    
    def __init__(self, seller_id: int, buyer_id: int, car_name: str):
        super().__init__(timeout=None)
        self.seller_id = seller_id
        self.buyer_id = buyer_id
        self.car_name = car_name
        
        # Complete the deal button
        complete_button = discord.ui.Button(
            label='✅ Complete the deal',
            style=discord.ButtonStyle.green,
            custom_id=f'complete_deal_{uuid.uuid4()}'
        )
        complete_button.callback = self.complete_callback
        self.add_item(complete_button)
        
        # Cancel the deal button
        cancel_button = discord.ui.Button(
            label='❌ Cancel the deal',
            style=discord.ButtonStyle.red,
            custom_id=f'cancel_deal_{uuid.uuid4()}'
        )
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)
    
    async def complete_callback(self, interaction: discord.Interaction):
        """Handle complete deal button - works like /close command"""
        try:
            # Check if deal confirmation already exists
            from database_mysql import get_deal_confirmation, add_deal_confirmation
            
            channel_id = interaction.channel.id
            existing_confirmation = get_deal_confirmation(channel_id)
            if existing_confirmation:
                await interaction.response.send_message(
                    "Deal confirmation is already in progress for this channel.",
                    ephemeral=True
                )
                return
            
            # Disable all buttons immediately to prevent multiple clicks
            for item in self.children:
                item.disabled = True
            
            # Update the message with disabled buttons
            await interaction.response.edit_message(view=self)
            
            # Add deal confirmation to database
            add_deal_confirmation(channel_id, False, False)
            
            # Create confirmation embed and view
            try:
                seller = await interaction.client.fetch_user(self.seller_id)
                buyer = await interaction.client.fetch_user(self.buyer_id)
            except Exception as fetch_error:
                print(f"Error fetching users: {fetch_error}")
                await interaction.followup.send("Error: Could not fetch user information.", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🤝 Confirm Deal",
                description=f"**Car:** {self.car_name}\n**Seller:** {seller.mention}\n**Buyer:** {buyer.mention}\n\nBoth parties need to confirm this deal was completed successfully.",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Confirmation Status", 
                value=f"⏳ {buyer.mention} pending\n⏳ {seller.mention} pending", 
                inline=False
            )
            
            # Import here to avoid circular import issues
            from commands.deal_confirmation import DealConfirmationView
            
            # Create confirmation view
            view = DealConfirmationView(
                channel_id=channel_id,
                seller_id=self.seller_id,
                buyer_id=self.buyer_id,
                car_name=self.car_name,
                is_giveaway_claim=False
            )
            
            await interaction.followup.send(embed=embed, view=view)
            
        except ImportError as import_error:
            print(f"Import error in auction complete callback: {import_error}")
            try:
                await interaction.followup.send("Error: Could not load deal confirmation system.", ephemeral=True)
            except:
                pass
        except Exception as e:
            print(f"Error in auction complete callback: {e}")
            import traceback
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("Error starting deal confirmation.", ephemeral=True)
                else:
                    await interaction.followup.send("Error starting deal confirmation.", ephemeral=True)
            except:
                pass
    
    async def cancel_callback(self, interaction: discord.Interaction):
        """Handle cancel deal button - works like /cancel command"""
        try:
            # Disable all buttons immediately to prevent multiple clicks
            for item in self.children:
                item.disabled = True
            
            # Update the message with disabled buttons
            await interaction.response.edit_message(view=self)
            
            # Handle channel deletion
            from database_mysql import remove_active_deal, remove_deal_confirmation
            from .utils import log_channel_messages, private_channels_activity
            import asyncio
            
            channel_id = interaction.channel.id
            
            # Clean up database entries
            remove_active_deal(channel_id)
            remove_deal_confirmation(channel_id)
            if channel_id in private_channels_activity:
                del private_channels_activity[channel_id]
            
            # Send cancellation message
            cancel_embed = discord.Embed(
                title="❌ Deal Cancelled",
                description="The deal has been cancelled by one of the parties.\n\n⏳ This channel will be deleted in 10 seconds.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=cancel_embed)
            
            # Schedule channel deletion with logging
            async def delayed_deletion():
                await asyncio.sleep(10)
                try:
                    await log_channel_messages(interaction.client, interaction.channel)
                    await interaction.channel.delete(reason="Deal cancelled")
                    print(f"Deleted cancelled deal channel: {interaction.channel.name}")
                except Exception as e:
                    print(f"Error deleting deal channel: {e}")
            
            asyncio.create_task(delayed_deletion())
            
        except Exception as e:
            print(f"Error in auction cancel callback: {e}")
            try:
                await interaction.followup.send("Error cancelling deal.", ephemeral=True)
            except:
                pass

class AuctionModal(Modal, title='Create Auction Listing'):
    car_name = TextInput(
        label='Car Name',
        placeholder='e.g., Ferrari 488 GTB',
        style=TextStyle.short,
        required=True,
        max_length=100
    )
    starting_bid = TextInput(
        label='Starting Bid',
        placeholder='e.g., 100000',
        style=TextStyle.short,
        required=True,
        max_length=20
    )
    duration_hours = TextInput(
        label='Auction Duration (hours)',
        placeholder='1-24 hours',
        style=TextStyle.short,
        required=True,
        max_length=2
    )

    async def on_submit(self, interaction: Interaction):
        user_id = interaction.user.id

        # Check if user already has a pending listing
        pending_listing = get_pending_listing(user_id, 'auction')
        if pending_listing:
            await interaction.response.send_message(
                "You already have a pending auction listing awaiting an image. Please finish or cancel that one first.",
                ephemeral=True
            )
            return

        # Validate starting bid
        try:
            starting_bid = int(self.starting_bid.value.replace('$', '').replace(',', '').replace(' ', ''))
            if starting_bid <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message(
                "Starting bid must be a valid positive number!",
                ephemeral=True
            )
            return

        # Validate duration
        try:
            duration = int(self.duration_hours.value)
            if duration < 1 or duration > 24:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message(
                "Duration must be between 1 and 24 hours!",
                ephemeral=True
            )
            return

        # Resolve car shortcode
        from database import resolve_car_shortcode
        display_name, original_input, _ = resolve_car_shortcode(self.car_name.value)

        time_unit = "hours"
        embed = discord.Embed(
            title="🏁 Auction Started",
            description=f"**Car:** {display_name}\n"
                       f"**Starting Bid:** ${starting_bid:,}\n"
                       f"**Duration:** {duration} {time_unit}\n\n"
                       f"Now upload an image of your car in this channel to complete your auction.\n\n"
                       f"⏰ You have 90 seconds to upload the image.",
            color=discord.Color.orange()
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

        listing_data = {
            'car_name': display_name,  # Use resolved display name
            'original_input': original_input,  # Store original input
            'starting_bid': starting_bid,
            'duration_hours': duration,
            'channel_id': interaction.channel_id
        }
        add_pending_listing(user_id, 'auction', listing_data, interaction.channel_id)

        timeout_task = asyncio.create_task(
            listing_timeout(user_id, interaction.channel, 'auction')
        )



async def handle_auction_image_upload(bot, message):
    """Handle image upload for auction listings"""
    user_id = message.author.id

    # Check for pending auction listings in priority order (test first, then regular)
    pending_test_auction = get_pending_listing(user_id, 'auction-test')
    pending_regular_auction = get_pending_listing(user_id, 'auction')
    
    # Determine which auction to process (prioritize test auctions)
    if pending_test_auction:
        listing_data = pending_test_auction
        listing_type = 'auction-test'
        is_test = True
    elif pending_regular_auction:
        listing_data = pending_regular_auction
        listing_type = 'auction'
        is_test = False
    else:
        return False  # No pending auctions

    # Check if message has image attachments
    has_image = False
    image_url = None
    if message.attachments:
        for attachment in message.attachments:
            if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']):
                has_image = True
                image_url = attachment.url
                break

    if has_image:
        try:
            print(f"Processing {listing_type} image upload for user {user_id}: {listing_data['car_name']}")
            
            # Store the author before any operations
            stored_author = message.author

            # Save the image BEFORE deleting the message
            saved_image_url = await save_image_to_bot_channel(
                bot, image_url, "auction", listing_data['car_name'], stored_author.display_name
            )

            # Create auction in forum with the saved image URL
            await create_auction_thread(bot, stored_author, listing_data, saved_image_url)

            # Delete the user's original image upload message AFTER everything else succeeds
            try:
                await message.delete()
                print(f"Deleted user's auction image upload from {message.author} in #{message.channel.name}.")
            except discord.HTTPException as e:
                print(f"Failed to delete the user's image message: {e}")

            # Only remove pending listing if everything succeeded
            remove_pending_listing(user_id, listing_type)
            print(f"Successfully created {listing_type} for {listing_data['car_name']}")
            return True

        except Exception as e:
            print(f"Error processing auction image upload for user {user_id}: {e}")
            import traceback
            traceback.print_exc()
            
            # Clean up the pending listing on error
            remove_pending_listing(user_id, listing_type)
            try:
                await message.author.send(
                    f"There was an error processing your auction image. Please try creating the auction again with `/auction` or `/auction test:true`."
                )
            except discord.HTTPException:
                pass
            return True

    else:
        # If user uploaded something but it's not an image while pending
        try:
            await message.delete()
            await message.author.send(
                f"Your previous message in #{message.channel.name} has been deleted. "
                "Please upload a **valid image file** (PNG, JPG, GIF, WEBP) to finalize the car auction."
            )
        except discord.HTTPException as e:
            print(f"Failed to handle non-image message: {e}")
        return True

async def delete_after_delay(message, delay_seconds):
    """Delete a message after a specified delay"""
    try:
        await asyncio.sleep(delay_seconds)
        await message.delete()
    except discord.HTTPException:
        pass

async def create_auction_thread(bot, author, listing_data, image_url):
    """Create a new auction thread in the forum"""
    forum_channel = bot.get_channel(AUCTION_FORUM_ID)
    if not forum_channel:
        print("ERROR: Could not access AUCTION HOUSE forum channel!")
        raise Exception("Could not access auction forum channel")

    # Create auction data
    auction_id = str(uuid.uuid4())
    print(f"Creating auction thread with ID: {auction_id} for {listing_data['car_name']}")

    # Handle both test auctions (minutes) and regular auctions (hours)
    is_test = listing_data.get('is_test', False)
    if is_test:
        # For test auctions, check both duration_minutes and duration_hours fields
        duration_minutes = listing_data.get('duration_minutes', listing_data.get('duration_hours', 1))
        end_time = datetime.utcnow() + timedelta(minutes=duration_minutes)
        duration_text = f"{duration_minutes} minute{'s' if duration_minutes != 1 else ''}"
        delay_seconds = duration_minutes * 60
        warning_delay = delay_seconds - 60  # 1 minute before end for test auctions
        thread_prefix = "🧪"  # Test indicator
    else:
        duration_hours = listing_data.get('duration_hours', 1)
        end_time = datetime.utcnow() + timedelta(hours=duration_hours)
        duration_text = f"{duration_hours} hour{'s' if duration_hours != 1 else ''}"
        delay_seconds = duration_hours * 3600
        warning_delay = delay_seconds - 300  # 5 minutes before end for regular auctions
        thread_prefix = "🚗"

    # Create the embed with image first
    embed = discord.Embed(
        title=f"🏁 **{listing_data['car_name'].upper()}**",
        description=f"**Starting Bid:** ${listing_data['starting_bid']:,}\n**Duration:** {duration_text}\n**Ends:** <t:{int(end_time.timestamp())}:F>\n\n🏁 **AUCTION STARTED!**\n\nPlace your bids below! Each bid must be higher than the previous one.",
        color=discord.Color.orange()
    )
    embed.set_image(url=image_url)

    # Get user's trader role for display
    try:
        from .trader_roles import get_user_trader_role_info
        role_info = await get_user_trader_role_info(bot, author.id)
        if role_info:
            footer_text = f'Auction by {author.display_name} • {role_info["role_name"]}'
        else:
            footer_text = f'Auction by {author.display_name} • No Trader Role'
    except Exception as e:
        print(f"Error getting trader role for embed: {e}")
        footer_text = f'Auction by {author.display_name}'

    embed.set_footer(text=footer_text, icon_url=author.avatar.url if author.avatar else None)

    # Create the thread with the embed as the first message
    try:
        thread_with_message = await forum_channel.create_thread(
            name=f"{thread_prefix} {listing_data['car_name']} - ${listing_data['starting_bid']:,}",
            content="Auction starting..."
        )
        # Get the actual thread object and send the embed
        thread = thread_with_message.thread
        await thread.send(embed=embed)

        # Create auction data for database
        auction_data = {
            'auction_id': auction_id,
            'thread_id': thread.id,
            'car_name': listing_data['car_name'],
            'starting_bid': listing_data['starting_bid'],
            'highest_bid': listing_data['starting_bid'],
            'highest_bidder': None,
            'seller_id': author.id,
            'end_time': end_time.isoformat(),
            'status': 'active',
            'is_test': is_test
        }

        # Store duration appropriately
        if is_test:
            auction_data['duration_minutes'] = duration_minutes
        else:
            auction_data['duration_hours'] = listing_data.get('duration_hours', 1)

        # Save to database
        add_active_auction(auction_data)

        # Process car recognition
        from .car_recognition import process_car_listing
        process_car_listing(listing_data['car_name'], 'auction', author.id, thread.id)

        # Schedule auction end
        asyncio.create_task(end_auction_timer(bot, auction_id, delay_seconds))

        # Schedule ending soon warning
        if warning_delay > 0:
            asyncio.create_task(auction_ending_soon_warning(bot, auction_id, warning_delay))

        print(f"Created {'test ' if is_test else ''}auction thread: {thread.name}")

    except Exception as e:
        print(f"Failed to create auction thread: {e}")

async def handle_auction_bid(bot, message):
    """Handle bidding in auction threads"""
    if message.author == bot.user:
        return

    # Find the auction for this thread
    all_auctions = get_all_active_auctions()
    auction = None
    auction_id = None
    for aid, auction_data in all_auctions.items():
        if auction_data['thread_id'] == message.channel.id:
            auction = auction_data
            auction_id = aid
            break

    if not auction:
        return  # Not an active auction thread

    # Check if the user is the auction creator/seller
    if message.author.id == auction['seller_id']:
        try:
            await message.delete()
            warning = await message.channel.send(
                f"{message.author.mention}, you cannot bid on your own auction!"
            )
            await asyncio.sleep(5)
            await warning.delete()
        except discord.HTTPException:
            pass
        return

    # Check if the user is already the highest bidder
    if auction['highest_bidder'] and message.author.id == auction['highest_bidder']:
        try:
            await message.delete()
            warning = await message.channel.send(
                f"{message.author.mention}, you are already the highest bidder. You cannot outbid yourself!"
            )
            await asyncio.sleep(5)
            await warning.delete()
        except discord.HTTPException:
            pass
        return

    # Check if message is a valid bid
    try:
        # More robust input cleaning
        clean_content = message.content.strip()
        if not clean_content:
            return

        # Remove common symbols and spaces
        clean_bid = clean_content.replace('$', '').replace(',', '').replace(' ', '').replace('.', '')

        # Validate it's only digits
        if not clean_bid.isdigit():
            raise ValueError("Not a valid number")

        bid_amount = int(clean_bid)

        # Check for reasonable bid limits
        if bid_amount <= 0:
            try:
                await message.delete()
                warning = await message.channel.send(
                    f"{message.author.mention}, bid amount must be greater than 0!"
                )
                await asyncio.sleep(5)
                await warning.delete()
            except discord.HTTPException:
                pass
            return

        if bid_amount > 999999999:  # Reasonable upper limit
            try:
                await message.delete()
                warning = await message.channel.send(
                    f"{message.author.mention}, bid amount is too large! Maximum bid is $999,999,999."
                )
                await asyncio.sleep(5)
                await warning.delete()
            except discord.HTTPException:
                pass
            return

        if bid_amount <= auction['highest_bid']:
            # Invalid bid - delete and warn
            try:
                await message.delete()
                warning = await message.channel.send(
                    f"{message.author.mention}, your bid of ${bid_amount:,} must be higher than the current highest bid of ${auction['highest_bid']:,}!"
                )
                await asyncio.sleep(5)
                await warning.delete()
            except discord.HTTPException:
                pass
            return

        # Store previous highest bidder for notification
        previous_bidder_id = auction['highest_bidder']

        # Valid bid - update auction in database
        update_auction_bid(auction_id, bid_amount, message.author.id)

        # Send DM to previous highest bidder if they exist
        if previous_bidder_id and previous_bidder_id != message.author.id:
            try:
                previous_bidder = await bot.fetch_user(previous_bidder_id)
                outbid_embed = discord.Embed(
                    title="😔 You've Been Outbid!",
                    description=f"Your bid on **{auction['car_name']}** has been outbid!\n\n**New Highest Bid:** ${bid_amount:,}\n**Current Leader:** {message.author.display_name}",
                    color=discord.Color.red()
                )
                outbid_embed.add_field(
                    name="Quick Action",
                    value=f"[Jump to Auction](<https://discord.com/channels/{message.guild.id}/{message.channel.id}>)",
                    inline=False
                )
                await previous_bidder.send(embed=outbid_embed)
            except Exception:
                # Silently ignore DM failures
                pass

        # Send confirmation message first (more important than title update)
        embed = discord.Embed(
            title="✅ New Highest Bid!",
            description=f"**{message.author.display_name}** bid **${bid_amount:,}**",
            color=discord.Color.green()
        )

        try:
            end_time = datetime.fromisoformat(auction['end_time'])
            embed.add_field(
                name="Auction Ends",
                value=f"<t:{int(end_time.timestamp())}:R>",
                inline=True
            )
        except Exception as e:
            print(f"Error adding end time to embed: {e}")

        # Always send confirmation message for valid bids
        confirmation_sent = False
        try:
            confirmation_msg = await message.channel.send(embed=embed)
            confirmation_sent = True
            print(f"✅ Sent bid confirmation for ${bid_amount:,} by {message.author.display_name}")

            # Delete the confirmation message after 5 seconds to keep the thread clean
            asyncio.create_task(delete_after_delay(confirmation_msg, 5))
        except discord.HTTPException as e:
            print(f"❌ Failed to send bid confirmation: {e}")
        except Exception as e:
            print(f"❌ Unexpected error sending bid confirmation: {e}")

        # Update thread title (do this after confirmation message)
        title_updated = False
        try:
            thread_prefix = "🧪" if auction.get('is_test', False) else "🚗"
            new_title = f"{thread_prefix} {auction['car_name']} - ${bid_amount:,}"
            await message.channel.edit(name=new_title)
            title_updated = True
            print(f"✅ Updated thread title to: {new_title}")
        except discord.HTTPException as e:
            print(f"❌ Failed to update thread title (HTTP error): {e}")
        except Exception as e:
            print(f"❌ Unexpected error updating thread title: {e}")

        # Log the results for debugging
        print(f"Bid processing complete - Confirmation sent: {confirmation_sent}, Title updated: {title_updated}")

    except (ValueError, OverflowError):
        # Not a valid number - delete the message
        try:
            await message.delete()
            warning = await message.channel.send(
                f"{message.author.mention}, please only send bid amounts as numbers in this auction thread!"
            )
            await asyncio.sleep(3)
            await warning.delete()
        except discord.HTTPException:
            pass
    except Exception as e:
        print(f"Error handling auction bid: {e}")
        try:
            await message.delete()
        except discord.HTTPException:
            pass

async def end_auction_timer(bot, auction_id, delay_seconds):
    """Timer to end an auction"""
    await asyncio.sleep(delay_seconds)
    await end_auction(bot, auction_id)

async def auction_ending_soon_warning(bot, auction_id, delay_seconds):
    """Send a warning before auction ends"""
    await asyncio.sleep(delay_seconds)

    auction = get_active_auction(auction_id)
    if not auction:
        return  # Auction already ended

    try:
        thread = bot.get_channel(auction['thread_id'])
        if thread:
            is_test = auction.get('is_test', False)
            warning_time = "1 minute" if is_test else "5 minutes"

            embed = discord.Embed(
                title="⏰ Auction Ending Soon!",
                description=f"**{auction['car_name']}** auction ends in **{warning_time}**!\n\n**Current Highest Bid:** ${auction['highest_bid']:,}",
                color=discord.Color.yellow()
            )
            embed.add_field(
                name="🚨 Last Chance!",
                value="Place your final bids now before it's too late!",
                inline=False
            )

            await thread.send(embed=embed)
    except Exception as e:
        print(f"Failed to send ending soon warning for auction {auction_id}: {e}")

async def end_auction(bot, auction_id):
    """End an auction and send seller confirmation"""
    auction = get_active_auction(auction_id)
    if not auction:
        print(f"Warning: Auction {auction_id} not found in active auctions")
        return

    try:
        # Mark auction as ended to prevent duplicate processing
        update_auction_status(auction_id, 'ended')

        # Get the auction thread
        thread = bot.get_channel(auction['thread_id'])
        if not thread:
            print(f"Warning: Could not find auction thread {auction['thread_id']}")
            # Still remove from active auctions even if thread not found
            remove_active_auction(auction_id)
            return

        if auction['highest_bidder']:
            # Send auction ended message to thread
            try:
                winner = await bot.fetch_user(auction['highest_bidder'])
                embed = discord.Embed(
                    title="🏆 AUCTION ENDED!",
                    description=f"**Highest Bidder:** {winner.mention}\n**Final Bid:** ${auction['highest_bid']:,}\n**Car:** {auction['car_name']}\n\n⏳ Waiting for seller to accept or reject the final bid...",
                    color=discord.Color.gold()
                )
            except discord.NotFound:
                embed = discord.Embed(
                    title="🏆 AUCTION ENDED!",
                    description=f"**Highest Bidder:** <@{auction['highest_bidder']}>\n**Final Bid:** ${auction['highest_bid']:,}\n**Car:** {auction['car_name']}\n\n⏳ Waiting for seller to accept or reject the final bid...",
                    color=discord.Color.gold()
                )
            except Exception as e:
                print(f"Error fetching winner user: {e}")
                embed = discord.Embed(
                    title="🏆 AUCTION ENDED!",
                    description=f"**Final Bid:** ${auction['highest_bid']:,}\n**Car:** {auction['car_name']}\n\n⏳ Waiting for seller to accept or reject the final bid...",
                    color=discord.Color.gold()
                )

            await thread.send(embed=embed)

            # Send seller confirmation DM
            await send_seller_confirmation(bot, auction_id, auction)
        else:
            # No bids case - log to ended auctions and clean up
            try:
                seller = await bot.fetch_user(auction['seller_id'])
                seller_name = seller.display_name if seller else 'Unknown'

                # Log the no-bids auction to ended auctions
                ended_auction_data = {
                    'auction_id': auction_id,
                    'car_name': auction['car_name'],
                    'auction_creator': {
                        'user_id': auction['seller_id'],
                        'username': seller_name
                    },
                    'final_bid': auction['starting_bid'],
                    'winner': {
                        'user_id': 0,  # Use 0 instead of None
                        'username': 'No Bidders'
                    },
                    'result': 'no_bids',
                    'timestamp': datetime.utcnow().isoformat(),
                    'is_test': auction.get('is_test', False)
                }
                add_ended_auction(ended_auction_data)

                # Post to ended auctions thread
                await post_no_bids_to_ended_auctions_thread(bot, auction, seller_name)

                # Send DM to the auction creator
                dm_embed = discord.Embed(
                    title="📢 Auction Ended - No Bids",
                    description=f"Your auction for **{auction['car_name']}** has ended without any bids.",
                    color=discord.Color.red()
                )
                await seller.send(embed=dm_embed)
                print(f"Sent no-bids DM to seller for auction: {auction['car_name']}")

            except discord.Forbidden:
                print(f"Could not send DM to seller {auction['seller_id']}")
            except Exception as e:
                print(f"Error processing no-bids auction: {e}")

            # Remove from active auctions
            remove_active_auction(auction_id)

            # Delete the thread after logging and notifying seller
            try:
                await asyncio.sleep(5)  # Give time for any final processing
                await thread.delete()
                print(f"Deleted auction thread with no bids: {auction['car_name']}")
            except Exception as e:
                print(f"Failed to delete auction thread with no bids: {e}")

    except Exception as e:
        print(f"Error ending auction {auction_id}: {e}")
        # Clean up on error
        try:
            update_auction_status(auction_id, 'expired')
            remove_active_auction(auction_id)
        except Exception as cleanup_error:
            print(f"Error during auction cleanup: {cleanup_error}")

async def send_seller_confirmation(bot, auction_id, auction):
    """Send seller confirmation DM with accept/reject buttons"""
    try:
        seller = await bot.fetch_user(auction['seller_id'])
        winner = await bot.fetch_user(auction['highest_bidder'])

        embed = discord.Embed(
            title="🔔 Auction Ended - Your Decision Required",
            description=f"Your auction for **{auction['car_name']}** has ended!\n\n**Highest Bidder:** {winner.display_name}\n**Final Bid:** ${auction['highest_bid']:,}\n\nDo you accept this final bid?",
            color=discord.Color.blue()
        )

        # Create persistent view with accept/reject buttons
        view = AuctionConfirmationView(auction_id)

        await seller.send(embed=embed, view=view)

    except discord.Forbidden:
        print(f"Could not send DM to seller {auction['seller_id']}")
        update_auction_status(auction_id, 'expired')
    except Exception as e:
        print(f"Error sending seller confirmation: {e}")
        update_auction_status(auction_id, 'expired')

async def handle_auction_accept(bot, interaction, auction_id):
    """Handle seller accepting the auction price"""
    auction = get_active_auction(auction_id)
    if not auction:
        try:
            await interaction.followup.send(
                "This auction is no longer active.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Could not send auction not found message: {e}")
        return

    # Check if auction is already closed to prevent duplicate processing
    if auction['status'] != 'active' and auction['status'] != 'ended':
        try:
            await interaction.followup.send(
                "This auction has already been processed.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Could not send auction already processed message: {e}")
        return

    try:
        # Mark auction as closed immediately to prevent duplicate processing
        update_auction_status(auction_id, 'closed')

        seller = await bot.fetch_user(auction['seller_id'])
        buyer = await bot.fetch_user(auction['highest_bidder'])

        # Find a mutual guild
        guild = None
        for g in bot.guilds:
            if g.get_member(auction['seller_id']) and g.get_member(auction['highest_bidder']):
                guild = g
                break

        if not guild:
            try:
                await interaction.response.send_message(
                    "Error: Could not find a mutual server to create the deal channel.",
                    ephemeral=True
                )
            except discord.InteractionResponse:
                await interaction.followup.send(
                    "Error: Could not find a mutual server to create the deal channel.",
                    ephemeral=True
                )
            return

        # Create private channel for the deal
        member_role = guild.get_role(config.MEMBER_ROLE_ID)  # Member role from rules
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            seller: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            buyer: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True, attach_files=True, embed_links=True)
        }

        # Add member role permissions if it exists
        if member_role:
            overwrites[member_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)

        channel = await guild.create_text_channel(
            name=f'auction-deal-{seller.name}-{buyer.name}',
            overwrites=overwrites,
            topic=f'Private auction deal between {seller.display_name} and {buyer.display_name}'
        )

        # Track channel activity
        private_channels_activity[channel.id] = asyncio.get_event_loop().time()

        # Track the deal for sales confirmation
        add_active_deal(channel.id, auction['seller_id'], auction['highest_bidder'], auction['car_name'])

        # Send initial message to the private channel
        view = AuctionDealChannelView(auction['seller_id'], auction['highest_bidder'], auction['car_name'])
        await channel.send(f"🏆 **Auction Deal Accepted**\n\nSeller: {seller.mention}\nBuyer: {buyer.mention}\n\n🚗 **Car:** {auction['car_name']}\n💰 **Final Bid:** ${auction['highest_bid']:,}\n\nPlease complete your transaction here. Remember to exchange in-game IDs only!\n\n💡 **Commands:**\n• `/close` - Complete and confirm the sale\n• `/cancel` - Cancel the deal and close this channel", view=view)
        await send_security_notice(channel)

        # Send DMs to both users (only once)
        channel_link = f"https://discord.com/channels/{guild.id}/{channel.id}"

        seller_dm_embed = discord.Embed(
            title="✅ Auction Deal Accepted",
            description=f"You have accepted the final bid of **${auction['highest_bid']:,}** for your **{auction['car_name']}**.\n\nA private channel has been created for you to complete the deal.",
            color=discord.Color.green()
        )
        seller_dm_embed.add_field(
            name="Deal Channel",
            value=f"[Click here to access the deal channel]({channel_link})",
            inline=False
        )

        buyer_dm_embed = discord.Embed(
            title="🎉 Auction Won!",
            description=f"Congratulations! The seller has accepted your winning bid of **${auction['highest_bid']:,}** for **{auction['car_name']}**.\n\nA private channel has been created for you to complete the deal.",
            color=discord.Color.green()
        )
        buyer_dm_embed.add_field(
            name="Deal Channel",
            value=f"[Click here to access the deal channel]({channel_link})",
            inline=False
        )

        # Send DMs with error handling
        dm_errors = []
        try:
            await seller.send(embed=seller_dm_embed)
            print(f"✅ Sent deal channel DM to seller {seller.display_name}")
        except discord.Forbidden:
            dm_errors.append(f"seller {seller.display_name}")
            print(f"Could not send DM to seller {seller.display_name}")

        try:
            await buyer.send(embed=buyer_dm_embed)
            print(f"✅ Sent deal channel DM to buyer {buyer.display_name}")
        except discord.Forbidden:
            dm_errors.append(f"buyer {buyer.display_name}")
            print(f"Could not send DM to buyer {buyer.display_name}")

        # Log the ended auction
        try:
            seller_name = seller.display_name if seller else 'Unknown'
            buyer_name = buyer.display_name if buyer else 'Unknown'

            # Add to ended auctions log
            ended_auction_data = {
                'auction_id': auction_id,
                'car_name': auction['car_name'],
                'auction_creator': {
                    'user_id': auction['seller_id'],
                    'username': seller_name
                },
                'final_bid': auction['highest_bid'],
                'winner': {
                    'user_id': auction['highest_bidder'],
                    'username': buyer_name
                },
                'result': 'accepted',
                'timestamp': datetime.utcnow().isoformat(),
                'is_test': auction.get('is_test', False)
            }
            add_ended_auction(ended_auction_data)

            # Post to ended auctions thread
            await post_to_ended_auctions_thread(bot, auction, seller_name, buyer_name)

        except Exception as e:
            print(f"Error with logging/posting: {e}")

        # Update the seller's response
        accepted_embed = discord.Embed(
            title="✅ Auction Deal Accepted",
            description=f"You have accepted the final bid of **${auction['highest_bid']:,}** for your **{auction['car_name']}**.\n\nA private deal channel has been created: {channel.mention}\n\n**Channel Link:** {channel_link}",
            color=discord.Color.green()
        )

        # Remove from active auctions
        remove_active_auction(auction_id)

        # Delete the auction thread after everything is completed
        try:
            thread = bot.get_channel(auction['thread_id'])
            if thread:
                await thread.delete()
                print(f"Deleted accepted auction thread: {auction['car_name']}")
        except Exception as e:
            print(f"Failed to delete auction thread: {e}")

        # Respond to the interaction  
        try:
            await interaction.edit_original_response(embed=accepted_embed, view=None)
        except discord.NotFound:
            # Original message was deleted, send a new message instead
            try:
                await interaction.followup.send(embed=accepted_embed, ephemeral=True)
            except Exception as followup_error:
                print(f"Could not send followup message: {followup_error}")
        except Exception as edit_error:
            print(f"Could not edit original message: {edit_error}")
            try:
                await interaction.followup.send(embed=accepted_embed, ephemeral=True)
            except Exception as followup_error:
                print(f"Could not send followup message: {followup_error}")

        print(f"✅ Successfully processed auction accept for {auction['car_name']}")

    except Exception as e:
        print(f"Error handling auction accept: {e}")
        # Revert status if there was an error
        update_auction_status(auction_id, 'active')
        try:
            await interaction.followup.send(
                f"Error creating deal channel: {str(e)}",
                ephemeral=True
            )
        except Exception:
            print(f"Could not send error message to user")

async def handle_auction_reject(bot, interaction, auction_id):
    """Handle seller rejecting the auction price"""
    auction = get_active_auction(auction_id)
    if not auction:
        try:
            await interaction.followup.send(
                "This auction is no longer active.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Could not send auction not found message: {e}")
        return

    # Check if auction is already closed to prevent duplicate processing
    if auction['status'] != 'active' and auction['status'] != 'ended':
        try:
            await interaction.followup.send(
                "This auction has already been processed.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Could not send auction already processed message: {e}")
        return

    try:
        # Mark auction as closed immediately to prevent duplicate processing
        update_auction_status(auction_id, 'closed')

        buyer = await bot.fetch_user(auction['highest_bidder'])

        # Send DM to buyer about rejection (only once)
        buyer_dm_embed = discord.Embed(
            title="❌ Auction Cancelled",
            description=f"Unfortunately, the seller has decided not to accept your winning bid of **${auction['highest_bid']:,}** for **{auction['car_name']}**.\n\nThe auction has been cancelled.",
            color=discord.Color.red()
        )

        try:
            await buyer.send(embed=buyer_dm_embed)
            print(f"✅ Sent rejection DM to buyer {buyer.display_name}")
        except discord.Forbidden:
            print(f"Could not send DM to buyer {buyer.display_name}")

        # Log the ended auction
        try:
            seller = await bot.fetch_user(auction['seller_id'])
            seller_name = seller.display_name if seller else 'Unknown'
            buyer_name = buyer.display_name if buyer else 'Unknown'

            ended_auction_data = {
                'auction_id': auction_id,
                'car_name': auction['car_name'],
                'auction_creator': {
                    'user_id': auction['seller_id'],
                    'username': seller_name
                },
                'final_bid': auction['highest_bid'],
                'winner': {
                    'user_id': auction['highest_bidder'],
                    'username': buyer_name
                },
                'result': 'rejected',
                'timestamp': datetime.utcnow().isoformat(),
                'is_test': auction.get('is_test', False)
            }
            add_ended_auction(ended_auction_data)
        except Exception as e:
            print(f"Error logging rejected auction: {e}")

        # Update the seller's response
        rejected_embed = discord.Embed(
            title="❌ Auction Cancelled",
            description=f"You have rejected the final bid of **${auction['highest_bid']:,}** for your **{auction['car_name']}**.\n\nThe auction has been cancelled and the bidder has been notified.",
            color=discord.Color.red()
        )

        # Remove from active auctions
        remove_active_auction(auction_id)

        # Delete the auction thread after everything is completed
        try:
            thread = bot.get_channel(auction['thread_id'])
            if thread:
                await thread.delete()
                print(f"Deleted rejected auction thread: {auction['car_name']}")
        except Exception as e:
            print(f"Failed to delete auction thread: {e}")

        # Respond to the interaction
        try:
            await interaction.edit_original_response(embed=rejected_embed, view=None)
        except discord.NotFound:
            # Original message was deleted, send a new message instead
            try:
                await interaction.followup.send(embed=rejected_embed, ephemeral=True)
            except Exception as followup_error:
                print(f"Could not send followup message: {followup_error}")
        except Exception as edit_error:
            print(f"Could not edit original message: {edit_error}")
            try:
                await interaction.followup.send(embed=rejected_embed, ephemeral=True)
            except Exception as followup_error:
                print(f"Could not send followup message: {followup_error}")

        print(f"✅ Successfully processed auction reject for {auction['car_name']}")

    except Exception as e:
        print(f"Error handling auction reject: {e}")
        # Revert status if there was an error
        update_auction_status(auction_id, 'active')
        try:
            await interaction.followup.send(
                f"Error processing rejection: {str(e)}",
                ephemeral=True
            )
        except Exception:
            print(f"Could not send error message to user")

async def post_to_ended_auctions_thread(bot, auction, seller_name, winner_name):
    """Post accepted auction to ended auctions thread"""
    try:
        ENDED_AUCTIONS_THREAD_ID = config.ENDED_AUCTIONS_THREAD_ID
        thread = bot.get_channel(ENDED_AUCTIONS_THREAD_ID)

        if not thread:
            print(f"Could not find ended auctions thread {ENDED_AUCTIONS_THREAD_ID}")
            return

        embed = discord.Embed(
            title="🏆 Auction Completed",
            description=f"**Car:** {auction['car_name']}\n**Seller:** {seller_name}\n**Winner:** {winner_name}\n**Final Bid:** ${auction['highest_bid']:,}",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )

        if auction.get('is_test', False):
            embed.set_footer(text="Test Auction")

        await thread.send(embed=embed)
        print(f"Posted to ended auctions thread: {auction['car_name']}")

    except Exception as e:
        print(f"Error posting to ended auctions thread: {e}")

async def post_no_bids_to_ended_auctions_thread(bot, auction, seller_name):
    """Post no-bids auction to ended auctions thread"""
    try:
        ENDED_AUCTIONS_THREAD_ID = config.ENDED_AUCTIONS_THREAD_ID
        thread = bot.get_channel(ENDED_AUCTIONS_THREAD_ID)

        if not thread:
            print(f"Could not find ended auctions thread {ENDED_AUCTIONS_THREAD_ID}")
            return

        embed = discord.Embed(
            title="📝 Auction Ended - No Bids",
            description=f"**Car:** {auction['car_name']}\n**Seller:** {seller_name}\n**Starting Bid:** ${auction['starting_bid']:,}\n**Result:** No bids received",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )

        if auction.get('is_test', False):
            embed.set_footer(text="Test Auction")

        await thread.send(embed=embed)
        print(f"Posted no-bids auction to ended auctions thread: {auction['car_name']}")

    except Exception as e:
        print(f"Error posting no-bids auction to ended auctions thread: {e}")

async def cleanup_pending_auction_listings():
    """Clean up any stuck pending auction listings on bot startup"""
    try:
        # Get all pending auction listings
        from database_postgres import get_all_pending_listings, remove_pending_listing

        pending_auctions = get_all_pending_listings('auction')
        pending_test_auctions = get_all_pending_listings('auction-test')

        cleanup_count = 0

        # Clean up regular auction listings
        for user_id in list(pending_auctions.keys()):
            remove_pending_listing(user_id, 'auction')
            cleanup_count += 1

        # Clean up test auction listings
        for user_id in list(pending_test_auctions.keys()):
            remove_pending_listing(user_id, 'auction-test')
            cleanup_count += 1

        if cleanup_count > 0:
            print(f"Cleaned up {cleanup_count} stuck pending auction listings on startup")

    except Exception as e:
        print(f"Error cleaning up pending auction listings: {e}")

async def restore_active_auctions(bot):
    """Restore active auctions after bot restart"""
    # First clean up any stuck pending listings
    await cleanup_pending_auction_listings()

    all_auctions = get_all_active_auctions()

    if not all_auctions:
        print("No active auctions to restore")
        return

    print(f"Restoring {len(all_auctions)} active auctions")
    expired_count = 0
    loaded_count = 0

    for auction_id, auction_data in list(all_auctions.items()):
        try:
            end_time = datetime.fromisoformat(auction_data['end_time'])
            current_time = datetime.utcnow()

            if current_time > end_time:
                # Auction has ended while bot was offline - end it now
                print(f"Processing auction that ended while bot was offline: {auction_id}")
                asyncio.create_task(end_auction(bot, auction_id))
                expired_count += 1
            else:
                # Auction is still active, schedule its end
                remaining_time = (end_time - current_time).total_seconds()
                if remaining_time > 0:
                    asyncio.create_task(end_auction_timer(bot, auction_id, remaining_time))

                    # Schedule ending soon warning
                    is_test = auction_data.get('is_test', False)
                    warning_delay = remaining_time - (60 if is_test else 300)
                    if warning_delay > 0:
                        asyncio.create_task(auction_ending_soon_warning(bot, auction_id, warning_delay))

                    loaded_count += 1
                    print(f"Restored auction: {auction_data['car_name']} (ends in {remaining_time/3600:.1f} hours)")
                else:
                    # Edge case: auction should have ended but remaining time is 0 or negative
                    await end_auction(bot, auction_id)
                    expired_count += 1

        except Exception as e:
            print(f"Error restoring auction {auction_id}: {e}")
            try:
                remove_active_auction(auction_id)
            except Exception:
                pass
            expired_count += 1

    print(f"Loaded {loaded_count} active auctions from database, processed {expired_count} expired ones")

async def schedule_auction_end(bot, auction_id, delay_seconds):
    """Schedule an auction to end after a delay"""
    await asyncio.sleep(delay_seconds)
    await handle_auction_end(bot, auction_id)



async def process_no_bids_auction(bot, auction_id, auction_data):
    """Process an auction that ended with no bids"""
    try:
        # Log the no-bids auction to ended auctions
        seller = await bot.fetch_user(auction_data['seller_id'])
        seller_name = seller.display_name if seller else 'Unknown'

        ended_auction_data = {
            'auction_id': auction_id,
            'car_name': auction_data['car_name'],
            'auction_creator': {
                'user_id': auction_data['seller_id'],
                'username': seller_name
            },
            'final_bid': auction_data['starting_bid'],
            'winner': {
                'user_id': 0,  # Use 0 instead of None to satisfy NOT NULL constraint
                'username': 'No Bidders'
            },
            'result': 'no_bids',
            'timestamp': datetime.utcnow().isoformat(),
            'is_test': auction_data.get('is_test', False)
        }
        add_ended_auction(ended_auction_data)

        # Post to ended auctions thread
        await post_no_bids_to_ended_auctions_thread(bot, auction_data, seller_name)

        # Send DM to the auction creator
        try:
            dm_embed = discord.Embed(
                title="📢 Auction Ended - No Bids",
                description=f"Your auction for **{auction_data['car_name']}** has ended without any bids.",
                color=discord.Color.red()
            )
            await seller.send(embed=dm_embed)
            print(f"Sent no-bids DM to seller for auction: {auction_data['car_name']}")
        except discord.Forbidden:
            print(f"Could not send DM to seller {auction_data['seller_id']}")

        # Remove from active auctions
        remove_active_auction(auction_id)

        # Delete the thread
        thread = bot.get_channel(auction_data['thread_id'])
        if thread:
            try:
                await asyncio.sleep(10)  # Give time for users to see the explanation
                await thread.delete()
                print(f"Deleted auction thread with no bids: {auction_data['car_name']}")
            except Exception as e:
                print(f"Failed to delete auction thread with no bids: {e}")

    except Exception as e:
        print(f"Error processing no-bids auction {auction_id}: {e}")
        try:
            remove_active_auction(auction_id)
        except Exception:
            pass

async def process_missed_bids(bot, auction_id, auction_data, thread, end_time):
    """Process any bids that were made while the bot was offline"""
    try:
        print(f"Checking for missed bids in auction {auction_id}")

        # Get the last time bot was online (we'll use a reasonable estimate)
        # For now, we'll check messages from the last 24 hours or auction start
        auction_start_time = datetime.fromisoformat(auction_data['end_time']) - timedelta(
            hours=auction_data.get('duration_hours', 0),
            minutes=auction_data.get('duration_minutes', 0)
        )

        # Look for messages after auction start but before bot restart
        check_after = auction_start_time

        # Track the last bot message to estimate when bot went offline
        last_bot_message_time = None

        missed_bids = []
        processed_count = 0

        # Read through thread history
        async for message in thread.history(limit=500, after=check_after, oldest_first=True):
            processed_count += 1

            # Track bot messages to estimate offline period
            if message.author == bot.user:
                last_bot_message_time = message.created_at
                continue

            # Skip messages from auction seller
            if message.author.id == auction_data['seller_id']:
                continue

            # Skip messages after auction end time
            if message.created_at > end_time:
                continue

            # Skip messages that were likely processed while bot was online
            if last_bot_message_time and message.created_at <= last_bot_message_time:
                continue

            # Check if message looks like a bid
            try:
                clean_content = message.content.strip()
                if not clean_content:
                    continue

                # Remove common symbols and spaces
                clean_bid = clean_content.replace('$', '').replace(',', '').replace(' ', '').replace('.', '')

                # Validate it's only digits
                if not clean_bid.isdigit():
                    continue

                bid_amount = int(clean_bid)

                # Validate bid amount
                if bid_amount <= 0 or bid_amount > 999999999:
                    continue

                # Check if it's higher than current highest bid
                if bid_amount > auction_data['highest_bid']:
                    # Check if user is already highest bidder
                    if auction_data['highest_bidder'] != message.author.id:
                        missed_bids.append({
                            'amount': bid_amount,
                            'user_id': message.author.id,
                            'username': message.author.display_name,
                            'timestamp': message.created_at,
                            'message': message
                        })

            except (ValueError, OverflowError):
                continue

        print(f"Processed {processed_count} messages, found {len(missed_bids)} potential missed bids")

        # Sort missed bids by timestamp and process them in order
        missed_bids.sort(key=lambda x: x['timestamp'])

        processed_missed_bids = 0
        for bid_info in missed_bids:
            # Verify this bid is still valid (higher than current highest)
            current_auction = get_active_auction(auction_id)
            if not current_auction:
                break

            if bid_info['amount'] > current_auction['highest_bid']:
                # Update the auction with this bid
                old_highest_bidder = current_auction['highest_bidder']
                update_auction_bid(auction_id, bid_info['amount'], bid_info['user_id'])

                # Send DM to previous highest bidder if they exist
                if old_highest_bidder and old_highest_bidder != bid_info['user_id']:
                    try:
                        previous_bidder = await bot.fetch_user(old_highest_bidder)
                        outbid_embed = discord.Embed(
                            title="😔 You've Been Outbid! (Offline Bid Processed)",
                            description=f"Your bid on **{auction_data['car_name']}** has been outbid by a bid that was placed while the bot was offline!\n\n**New Highest Bid:** ${bid_info['amount']:,}\n**Current Leader:** {bid_info['username']}",
                            color=discord.Color.red()
                        )
                        outbid_embed.add_field(
                            name="Quick Action",
                            value=f"[Jump to Auction](<https://discord.com/channels/{thread.guild.id}/{thread.id}>)",
                            inline=False
                        )
                        await previous_bidder.send(embed=outbid_embed)
                    except Exception as dm_error:
                        print(f"Could not send outbid DM: {dm_error}")

                processed_missed_bids += 1
                print(f"Processed missed bid: ${bid_info['amount']:,} from {bid_info['username']}")

                # Update auction data for next iteration
                auction_data['highest_bid'] = bid_info['amount']
                auction_data['highest_bidder'] = bid_info['user_id']

        if processed_missed_bids > 0:
            print(f"Successfully processed {processed_missed_bids} missed bids for auction {auction_id}")

    except Exception as e:
        print(f"Error processing missed bids for auction {auction_id}: {e}")

async def handle_auction_end(bot, auction_id):
    """Handle auction ending - calls the main end_auction function"""
    try:
        await end_auction(bot, auction_id)
    except Exception as e:
        print(f"Error handling auction end for {auction_id}: {e}")

class AuctionModal(Modal, title="Create Auction"):
    car_name = TextInput(
        label="Car Name",
        placeholder="Enter the car name (e.g., BMW M3 F80)",
        style=TextStyle.short,
        max_length=100,
        required=True
    )

    starting_bid = TextInput(
        label="Starting Bid",
        placeholder="Enter starting bid amount (numbers only)",
        style=TextStyle.short,
        max_length=20,
        required=True
    )

    duration_hours = TextInput(
        label="Duration (Hours)",
        placeholder="Enter auction duration in hours (1-168)",
        style=TextStyle.short,
        max_length=3,
        required=True
    )

    description = TextInput(
        label="Description (Optional)",
        placeholder="Enter additional details about the car",
        style=TextStyle.paragraph,
        max_length=500,
        required=False
    )

    def __init__(self, is_test=False):
        super().__init__()
        self.is_test = is_test
        if is_test:
            self.title = "Create Test Auction"
            # Update the duration field for test auctions
            self.duration_hours.label = "Duration (Minutes)"
            self.duration_hours.placeholder = "Enter duration in minutes (1-10)"

    async def on_submit(self, interaction: Interaction):
        # Validate starting bid
        try:
            starting_bid_amount = int(self.starting_bid.value.replace(',', '').replace('$', ''))
            if starting_bid_amount <= 0:
                await interaction.response.send_message(
                    "Starting bid must be greater than 0.",
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid number for the starting bid.",
                ephemeral=True
            )
            return

        # Validate duration
        try:
            duration_value = int(self.duration_hours.value)
            if self.is_test:
                # For test auctions, validate minutes (1-10)
                if duration_value < 1 or duration_value > 10:
                    await interaction.response.send_message(
                        "Duration must be between 1 and 10 minutes for test auctions.",
                        ephemeral=True
                    )
                    return
                duration_field = 'duration_minutes'
            else:
                # For regular auctions, validate hours (1-168)
                if duration_value < 1 or duration_value > 168:
                    await interaction.response.send_message(
                        "Duration must be between 1 and 168 hours (1 week).",
                        ephemeral=True
                    )
                    return
                duration_field = 'duration_hours'
        except ValueError:
            await interaction.response.send_message(
                f"Please enter a valid number for duration.",
                ephemeral=True
            )
            return

        # Handle car disambiguation
        async def proceed_with_auction(interaction_or_followup, final_car_name):
            # Store pending auction data
            auction_data = {
                'car_name': final_car_name,
                'starting_bid': starting_bid_amount,
                duration_field: duration_value,
                'description': self.description.value,
                'is_test': self.is_test,
                'channel_id': interaction.channel_id
            }

            listing_type = 'auction-test' if self.is_test else 'auction'
            add_pending_listing(interaction.user.id, listing_type, auction_data, interaction.channel_id)

            # Set up timeout for image upload
            timeout_task = asyncio.create_task(
                listing_timeout(interaction.user.id, interaction.channel, listing_type)
            )

            time_unit = "minutes" if self.is_test else "hours"
            embed = discord.Embed(
                title="📸 Upload Image",
                description=f"Please upload an image of your **{final_car_name}** in this channel within 90 seconds.\n\n**Duration:** {duration_value} {time_unit}",
                color=discord.Color.blue()
            )

            # Send ephemeral message in the channel
            try:
                # Always use followup since this function is called after interaction responses
                await interaction_or_followup.followup.send(embed=embed, ephemeral=True)
            except Exception as e:
                print(f"Error sending auction confirmation: {e}")
                # If followup fails, the listing is still created so just log the error

        # Handle car disambiguation
        try:
            # Check if we need to respond to the modal first
            if not interaction.response.is_done():
                # Respond to the modal immediately with a thinking message
                await interaction.response.send_message("Processing your auction request...", ephemeral=True)

            await handle_car_disambiguation(interaction, self.car_name.value, interaction.user.id, proceed_with_auction)
        except Exception as e:
            print(f"Error in car disambiguation: {e}")
            # Fallback - proceed with original car name if disambiguation fails
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("Processing your auction request...", ephemeral=True)
                await proceed_with_auction(interaction, self.car_name.value)
            except Exception as fallback_error:
                print(f"Error in fallback: {fallback_error}")
                # Final fallback - just acknowledge the modal
                if not interaction.response.is_done():
                    await interaction.response.send_message("An error occurred. Please try again.", ephemeral=True)

def setup_auction_commands(tree):
    """Setup auction-related commands"""
    @tree.command(name="auction", description="Create a car auction")
    async def auction_command(interaction: Interaction):
        if interaction.channel_id != AUCTION_CHANNEL_ID:
            await interaction.response.send_message(
                "This command can only be used in the #make-auction channel.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(AuctionModal(is_test=False))

    @tree.command(name="test-auction", description="Create a test auction (Admin only)")
    async def test_auction_command(interaction: Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "This command is only available to administrators.",
                ephemeral=True
            )
            return

        if interaction.channel_id != AUCTION_CHANNEL_ID:
            await interaction.response.send_message(
                "This command can only be used in the #make-auction channel.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(AuctionModal(is_test=True))

async def handle_auction_image_upload(bot, message):
    """Handle image upload for auction listings"""
    user_id = message.author.id

    # Check for pending auction (regular or test)
    pending_auction = get_pending_listing(user_id, 'auction')
    pending_test_auction = get_pending_listing(user_id, 'auction-test')

    if not pending_auction and not pending_test_auction:
        return False

    # Determine which type of auction this is
    is_test = pending_test_auction is not None
    auction_data = pending_test_auction if is_test else pending_auction
    listing_type = 'auction-test' if is_test else 'auction'

    if not message.attachments:
        await message.delete()
        return True

    # Process the image upload
    try:
        # Save image to bot channel
        image_url = await save_image_to_bot_channel(
            bot, message.attachments[0].url, "auction", 
            auction_data['car_name'], message.author.display_name
        )

        # Create auction thread
        forum_channel = bot.get_channel(AUCTION_FORUM_ID)
        if not forum_channel:
            await message.author.send("Error: Could not find auction forum channel.")
            return True

        # Generate unique auction ID
        auction_id = str(uuid.uuid4())[:8]

        # Calculate end time based on auction type
        if is_test:
            duration_minutes = auction_data.get('duration_minutes', 1)
            end_time = datetime.now() + timedelta(minutes=duration_minutes)
        else:
            duration_hours = auction_data.get('duration_hours', 1)
            end_time = datetime.now() + timedelta(hours=duration_hours)

        # Create auction embed first
        embed = discord.Embed(
            title=f"🏁 {'TEST ' if is_test else ''}AUCTION: {auction_data['car_name'].upper()}",
            description=auction_data.get('description', ''),
            color=discord.Color.gold() if not is_test else discord.Color.orange()
        )

        embed.add_field(name="Starting Bid", value=f"${auction_data['starting_bid']:,}", inline=True)
        embed.add_field(name="Current Bid", value=f"${auction_data['starting_bid']:,}", inline=True)
        embed.add_field(name="Ends At", value=f"<t:{int(end_time.timestamp())}:F>", inline=True)

        if image_url:
            embed.set_image(url=image_url)

        embed.set_footer(text=f"Auction ID: {auction_id} | Hosted by {message.author.display_name}")

        # Create thread with embed as the first message
        thread_name = f"{'[TEST] ' if is_test else ''}{auction_data['car_name']} - ${auction_data['starting_bid']:,}"
        thread_with_message = await forum_channel.create_thread(
            name=thread_name,
            embed=embed
        )
        thread = thread_with_message.thread

        # Store auction data
        auction_db_data = {
            'auction_id': auction_id,
            'thread_id': thread.id,
            'car_name': auction_data['car_name'],
            'starting_bid': auction_data['starting_bid'],
            'highest_bid': auction_data['starting_bid'],
            'highest_bidder': None,
            'seller_id': user_id,
            'end_time': end_time.isoformat(),
            'status': 'active',
            'duration_hours': duration_hours if not is_test else 0,
            'duration_minutes': duration_minutes if is_test else 0,
            'is_test': is_test
        }

        add_active_auction(auction_db_data)

        # Schedule auction end
        if is_test:
            delay_seconds = duration_minutes * 60
        else:
            delay_seconds = duration_hours * 3600
        asyncio.create_task(schedule_auction_end(bot, auction_id, delay_seconds))

        # Clean up
        remove_pending_listing(user_id, listing_type)
        await message.delete()

        # Send confirmation
        confirm_embed = discord.Embed(
            title="✅ Auction Created!",
            description=f"Your {'test ' if is_test else ''}auction for **{auction_data['car_name']}** has been created successfully!",
            color=discord.Color.green()
        )
        confirm_embed.add_field(name="Auction Thread", value=thread.mention, inline=False)

        await message.author.send(embed=confirm_embed)

    except Exception as e:
        await message.author.send(f"Error creating auction: {str(e)}")
        remove_pending_listing(user_id, listing_type)

    return True

async def handle_auction_bid(bot, message):
    """Handle bidding in auction threads"""
    if message.author == bot.user:
        return

    # Find the auction for this thread
    all_auctions = get_all_active_auctions()
    auction = None
    auction_id = None
    for aid, auction_data in all_auctions.items():
        if auction_data['thread_id'] == message.channel.id:
            auction = auction_data
            auction_id = aid
            break

    if not auction:
        return  # Not an active auction thread

    # Check if the user is the auction creator/seller
    if message.author.id == auction['seller_id']:
        try:
            await message.delete()
            warning = await message.channel.send(
                f"{message.author.mention}, you cannot bid on your own auction!"
            )
            await asyncio.sleep(5)
            await warning.delete()
        except discord.HTTPException:
            pass
        return

    # Check if the user is already the highest bidder
    if auction['highest_bidder'] and message.author.id == auction['highest_bidder']:
        try:
            await message.delete()
            warning = await message.channel.send(
                f"{message.author.mention}, you are already the highest bidder. You cannot outbid yourself!"
            )
            await asyncio.sleep(5)
            await warning.delete()
        except discord.HTTPException:
            pass
        return

    # Check if message is a valid bid
    try:
        # More robust input cleaning
        clean_content = message.content.strip()
        if not clean_content:
            return

        # Remove common symbols and spaces
        clean_bid = clean_content.replace('$', '').replace(',', '').replace(' ', '').replace('.', '')

        # Validate it's only digits
        if not clean_bid.isdigit():
            raise ValueError("Not a valid number")

        bid_amount = int(clean_bid)

        # Check for reasonable bid limits
        if bid_amount <= 0:
            try:
                await message.delete()
                warning = await message.channel.send(
                    f"{message.author.mention}, bid amount must be greater than 0!"
                )
                await asyncio.sleep(5)
                await warning.delete()
            except discord.HTTPException:
                pass
            return

        if bid_amount > 999999999:  # Reasonable upper limit
            try:
                await message.delete()
                warning = await message.channel.send(
                    f"{message.author.mention}, bid amount is too large! Maximum bid is $999,999,999."
                )
                await asyncio.sleep(5)
                await warning.delete()
            except discord.HTTPException:
                pass
            return

        if bid_amount <= auction['highest_bid']:
            # Invalid bid - delete and warn
            try:
                await message.delete()
                warning = await message.channel.send(
                    f"{message.author.mention}, your bid of ${bid_amount:,} must be higher than the current highest bid of ${auction['highest_bid']:,}!"
                )
                await asyncio.sleep(5)
                await warning.delete()
            except discord.HTTPException:
                pass
            return

        # Store previous highest bidder for notification
        previous_bidder_id = auction['highest_bidder']

        # Valid bid - update auction in database
        update_auction_bid(auction_id, bid_amount, message.author.id)

        # Update the original auction embed with new highest bid
        embed_updated = False
        try:
            # Get the first message in the thread (the auction embed)
            async for msg in message.channel.history(limit=50, oldest_first=True):
                if msg.author == bot.user and msg.embeds:
                    embed = msg.embeds[0]
                    if "🏁" in embed.title and auction['car_name'].upper() in embed.title:
                        # Update the embed with new highest bid information
                        updated_embed = discord.Embed(
                            title=embed.title,
                            description=embed.description,
                            color=embed.color
                        )

                        # Add updated fields
                        updated_embed.add_field(name="Starting Bid", value=f"${auction['starting_bid']:,}", inline=True)
                        updated_embed.add_field(name="Highest Bid", value=f"${bid_amount:,}", inline=True)
                        updated_embed.add_field(name="Current Leader", value=message.author.display_name, inline=True)

                        # Add end time
                        try:
                            end_time = datetime.fromisoformat(auction['end_time'])
                            updated_embed.add_field(name="Ends At", value=f"<t:{int(end_time.timestamp())}:F>", inline=False)
                        except Exception:
                            pass

                        # Preserve image and footer
                        if embed.image:
                            updated_embed.set_image(url=embed.image.url)
                        if embed.footer:
                            updated_embed.set_footer(text=embed.footer.text, icon_url=embed.footer.icon_url)

                        # Update the message
                        await msg.edit(embed=updated_embed)
                        embed_updated = True
                        print(f"✅ Updated auction embed with new highest bid: ${bid_amount:,}")
                        break

            if not embed_updated:
                print(f"❌ Could not find auction embed to update")

        except Exception as e:
            print(f"❌ Error updating auction embed: {e}")

        # Send DM to previous highest bidder if they exist
        if previous_bidder_id and previous_bidder_id != message.author.id:
            try:
                previous_bidder = await bot.fetch_user(previous_bidder_id)
                outbid_embed = discord.Embed(
                    title="😔 You've Been Outbid!",
                    description=f"Your bid on **{auction['car_name']}** has been outbid!\n\n**New Highest Bid:** ${bid_amount:,}\n**Current Leader:** {message.author.display_name}",
                    color=discord.Color.red()
                )
                outbid_embed.add_field(
                    name="Quick Action",
                    value=f"[Jump to Auction](<https://discord.com/channels/{message.guild.id}/{message.channel.id}>)",
                    inline=False
                )
                await previous_bidder.send(embed=outbid_embed)
                print(f"✅ Sent outbid DM to user {previous_bidder.display_name}")
            except discord.Forbidden:
                print(f"❌ Could not send DM to user {previous_bidder_id} - DMs disabled")
            except Exception as e:
                print(f"❌ Failed to send outbid DM: {e}")

        # Send confirmation message first (more important than title update)
        embed = discord.Embed(
            title="✅ New Highest Bid!",
            description=f"**{message.author.display_name}** bid **${bid_amount:,}**",
            color=discord.Color.green()
        )

        try:
            end_time = datetime.fromisoformat(auction['end_time'])
            embed.add_field(
                name="Auction Ends",
                value=f"<t:{int(end_time.timestamp())}:R>",
                inline=True
            )
        except Exception as e:
            print(f"Error adding end time to embed: {e}")

        # Always send confirmation message for valid bids
        confirmation_sent = False
        try:
            confirmation_msg = await message.channel.send(embed=embed)
            confirmation_sent = True
            print(f"✅ Sent bid confirmation for ${bid_amount:,} by {message.author.display_name}")

            # Delete the confirmation message after 5 seconds to keep the thread clean
            asyncio.create_task(delete_after_delay(confirmation_msg, 5))
        except discord.HTTPException as e:
            print(f"❌ Failed to send bid confirmation: {e}")
        except Exception as e:
            print(f"❌ Unexpected error sending bid confirmation: {e}")

        # Update thread title (do this after confirmation message)
        title_updated = False
        try:
            thread_prefix = "🧪" if auction.get('is_test', False) else "🚗"
            new_title = f"{thread_prefix} {auction['car_name']} - ${bid_amount:,}"
            await message.channel.edit(name=new_title)
            title_updated = True
            print(f"✅ Updated thread title to: {new_title}")
        except discord.HTTPException as e:
            print(f"❌ Failed to update thread title (HTTP error): {e}")
        except Exception as e:
            print(f"❌ Unexpected error updating thread title: {e}")

        # Log the results for debugging
        print(f"Bid processing complete - Confirmation sent: {confirmation_sent}, Title updated: {title_updated}, Embed updated: {embed_updated}")

    except (ValueError, OverflowError):
        # Not a valid number - delete the message
        try:
            await message.delete()
            warning = await message.channel.send(
                f"{message.author.mention}, please only send bid amounts as numbers in this auction thread!"
            )
            await asyncio.sleep(3)
            await warning.delete()
        except discord.HTTPException:
            pass
    except Exception as e:
        print(f"Error handling auction bid: {e}")
        try:
            await message.delete()
        except discord.HTTPException:
            pass

async def handle_auction_accept(bot, interaction, auction_id):
    """Handle seller accepting the auction price"""
    auction = get_active_auction(auction_id)
    if not auction:
        try:
            await interaction.followup.send(
                "This auction is no longer active.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Could not send auction not found message: {e}")
        return

    # Check if auction is already closed to prevent duplicate processing
    if auction['status'] != 'active' and auction['status'] != 'ended':
        try:
            await interaction.followup.send(
                "This auction has already been processed.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Could not send auction already processed message: {e}")
        return

    try:
        # Mark auction as closed immediately to prevent duplicate processing
        update_auction_status(auction_id, 'closed')

        seller = await bot.fetch_user(auction['seller_id'])
        buyer = await bot.fetch_user(auction['highest_bidder'])

        # Find a mutual guild
        guild = None
        for g in bot.guilds:
            if g.get_member(auction['seller_id']) and g.get_member(auction['highest_bidder']):
                guild = g
                break

        if not guild:
            try:
                await interaction.response.send_message(
                    "Error: Could not find a mutual server to create the deal channel.",
                    ephemeral=True
                )
            except Exception:
                pass
            return

        # Create private channel for the deal
        member_role = guild.get_role(config.MEMBER_ROLE_ID)  # Member role from rules
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            seller: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            buyer: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True, attach_files=True, embed_links=True)
        }

        # Add member role permissions if it exists
        if member_role:
            overwrites[member_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)

        channel = await guild.create_text_channel(
            name=f'auction-deal-{seller.name}-{buyer.name}',
            overwrites=overwrites,
            topic=f'Private auction deal between {seller.display_name} and {buyer.display_name}'
        )

        # Track channel activity
        private_channels_activity[channel.id] = asyncio.get_event_loop().time()

        # Track the deal for sales confirmation
        add_active_deal(channel.id, auction['seller_id'], auction['highest_bidder'], auction['car_name'])

        # Send initial message to the private channel
        view = AuctionDealChannelView(auction['seller_id'], auction['highest_bidder'], auction['car_name'])
        await channel.send(f"🏆 **Auction Deal Accepted**\n\nSeller: {seller.mention}\nBuyer: {buyer.mention}\n\n🚗 **Car:** {auction['car_name']}\n💰 **Final Bid:** ${auction['highest_bid']:,}\n\nPlease complete your transaction here. Remember to exchange in-game IDs only!\n\n💡 **Commands:**\n• `/close` - Complete and confirm the sale\n• `/cancel` - Cancel the deal and close this channel", view=view)

        await send_security_notice(channel)

        # Send DMs to both users (only once)
        channel_link = f"https://discord.com/channels/{guild.id}/{channel.id}"

        seller_dm_embed = discord.Embed(
            title="✅ Auction Deal Accepted",
            description=f"You have accepted the final bid of **${auction['highest_bid']:,}** for your **{auction['car_name']}**.\n\nA private channel has been created for you to complete the deal.",
            color=discord.Color.green()
        )
        seller_dm_embed.add_field(
            name="Deal Channel",
            value=f"[Click here to access the deal channel]({channel_link})",
            inline=False
        )

        buyer_dm_embed = discord.Embed(
            title="🎉 Auction Won!",
            description=f"Congratulations! The seller has accepted your winning bid of **${auction['highest_bid']:,}** for **{auction['car_name']}**.\n\nA private channel has been created for you to complete the deal.",
            color=discord.Color.green()
        )
        buyer_dm_embed.add_field(
            name="Deal Channel",
            value=f"[Click here to access the deal channel]({channel_link})",
            inline=False
        )

        # Send DMs with error handling
        dm_errors = []
        try:
            await seller.send(embed=seller_dm_embed)
            print(f"✅ Sent deal channel DM to seller {seller.display_name}")
        except discord.Forbidden:
            dm_errors.append(f"seller {seller.display_name}")
            print(f"Could not send DM to seller {seller.display_name}")

        try:
            await buyer.send(embed=buyer_dm_embed)
            print(f"✅ Sent deal channel DM to buyer {buyer.display_name}")
        except discord.Forbidden:
            dm_errors.append(f"buyer {buyer.display_name}")
            print(f"Could not send DM to buyer {buyer.display_name}")

        # Log the ended auction
        try:
            seller_name = seller.display_name if seller else 'Unknown'
            buyer_name = buyer.display_name if buyer else 'Unknown'

            # Add to ended auctions log
            ended_auction_data = {
                'auction_id': auction_id,
                'car_name': auction['car_name'],
                'auction_creator': {
                    'user_id': auction['seller_id'],
                    'username': seller_name
                },
                'final_bid': auction['highest_bid'],
                'winner': {
                    'user_id': auction['highest_bidder'],
                    'username': buyer_name
                },
                'result': 'accepted',
                'timestamp': datetime.utcnow().isoformat(),
                'is_test': auction.get('is_test', False)
            }
            add_ended_auction(ended_auction_data)

            # Post to ended auctions thread
            await post_to_ended_auctions_thread(bot, auction, seller_name, buyer_name)

        except Exception as e:
            print(f"Error with logging/posting: {e}")

        # Update the seller's response
        accepted_embed = discord.Embed(
            title="✅ Auction Deal Accepted",
            description=f"You have accepted the final bid of **${auction['highest_bid']:,}** for your **{auction['car_name']}**.\n\nA private deal channel has been created: {channel.mention}\n\n**Channel Link:** {channel_link}",
            color=discord.Color.green()
        )

        # Remove from active auctions
        remove_active_auction(auction_id)

        # Delete the auction thread after everything is completed
        try:
            thread = bot.get_channel(auction['thread_id'])
            if thread:
                await thread.delete()
                print(f"Deleted accepted auction thread: {auction['car_name']}")
        except Exception as e:
            print(f"Failed to delete auction thread: {e}")

        # Respond to the interaction  
        try:
            await interaction.edit_original_response(embed=accepted_embed, view=None)
        except discord.NotFound:
            # Original message was deleted, send a new message instead
            try:
                await interaction.followup.send(embed=accepted_embed, ephemeral=True)
            except Exception as followup_error:
                print(f"Could not send followup message: {followup_error}")
        except Exception as edit_error:
            print(f"Could not edit original message: {edit_error}")
            try:
                await interaction.followup.send(embed=accepted_embed, ephemeral=True)
            except Exception as followup_error:
                print(f"Could not send followup message: {followup_error}")

        print(f"✅ Successfully processed auction accept for {auction['car_name']}")

    except Exception as e:
        print(f"Error handling auction accept: {e}")
        # Revert status if there was an error
        update_auction_status(auction_id, 'active')
        try:
            await interaction.followup.send(
                f"Error creating deal channel: {str(e)}",
                ephemeral=True
            )
        except Exception:
            print(f"Could not send error message to user")

async def handle_auction_reject(bot, interaction, auction_id):
    """Handle seller rejecting the auction price"""
    auction = get_active_auction(auction_id)
    if not auction:
        try:
            await interaction.followup.send(
                "This auction is no longer active.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Could not send auction not found message: {e}")
        return

    # Check if auction is already closed to prevent duplicate processing
    if auction['status'] != 'active' and auction['status'] != 'ended':
        try:
            await interaction.followup.send(
                "This auction has already been processed.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Could not send auction already processed message: {e}")
        return

    try:
        # Mark auction as closed immediately to prevent duplicate processing
        update_auction_status(auction_id, 'closed')

        buyer = await bot.fetch_user(auction['highest_bidder'])

        # Send DM to buyer about rejection (only once)
        buyer_dm_embed = discord.Embed(
            title="❌ Auction Cancelled",
            description=f"Unfortunately, the seller has decided not to accept your winning bid of **${auction['highest_bid']:,}** for **{auction['car_name']}**.\n\nThe auction has been cancelled.",
            color=discord.Color.red()
        )

        try:
            await buyer.send(embed=buyer_dm_embed)
            print(f"✅ Sent rejection DM to buyer {buyer.display_name}")
        except discord.Forbidden:
            print(f"Could not send DM to buyer {buyer.display_name}")

        # Log the ended auction
        try:
            seller = await bot.fetch_user(auction['seller_id'])
            seller_name = seller.display_name if seller else 'Unknown'
            buyer_name = buyer.display_name if buyer else 'Unknown'

            ended_auction_data = {
                'auction_id': auction_id,
                'car_name': auction['car_name'],
                'auction_creator': {
                    'user_id': auction['seller_id'],
                    'username': seller_name
                },
                'final_bid': auction['highest_bid'],
                'winner': {
                    'user_id': auction['highest_bidder'],
                    'username': buyer_name
                },
                'result': 'rejected',
                'timestamp': datetime.utcnow().isoformat(),
                'is_test': auction.get('is_test', False)
            }
            add_ended_auction(ended_auction_data)
        except Exception as e:
            print(f"Error logging rejected auction: {e}")

        # Update the seller's response
        rejected_embed = discord.Embed(
            title="❌ Auction Cancelled",
            description=f"You have rejected the final bid of **${auction['highest_bid']:,}** for your **{auction['car_name']}**.\n\nThe auction has been cancelled and the bidder has been notified.",
            color=discord.Color.red()
        )

        # Remove from active auctions
        remove_active_auction(auction_id)

        # Delete the auction thread after everything is completed
        try:
            thread = bot.get_channel(auction['thread_id'])
            if thread:
                await thread.delete()
                print(f"Deleted rejected auction thread: {auction['car_name']}")
        except Exception as e:
            print(f"Failed to delete auction thread: {e}")

        # Respond to the interaction
        try:
            await interaction.edit_original_response(embed=rejected_embed, view=None)
        except discord.NotFound:
            # Original message was deleted, send a new message instead
            try:
                await interaction.followup.send(embed=rejected_embed, ephemeral=True)
            except Exception as followup_error:
                print(f"Could not send followup message: {followup_error}")
        except Exception as edit_error:
            print(f"Could not edit original message: {edit_error}")
            try:
                await interaction.followup.send(embed=rejected_embed, ephemeral=True)
            except Exception as followup_error:
                print(f"Could not send followup message: {followup_error}")

        print(f"✅ Successfully processed auction reject for {auction['car_name']}")

    except Exception as e:
        print(f"Error handling auction reject: {e}")
        # Revert status if there was an error
        update_auction_status(auction_id, 'active')
        try:
            await interaction.followup.send(
                f"Error processing rejection: {str(e)}",
                ephemeral=True
            )
        except Exception:
            print(f"Could not send error message to user")

async def restore_active_auctions(bot):
    """Restore active auctions after bot restart"""
    all_auctions = get_all_active_auctions()
    current_time = datetime.utcnow()
    loaded_count = 0
    expired_count = 0

    for auction_id, auction_data in list(all_auctions.items()):
        try:
            required_fields = ['auction_id', 'end_time', 'thread_id', 'car_name', 'status']
            if not all(field in auction_data for field in required_fields):
                print(f"Skipping incomplete auction data: missing required fields")
                continue

            if auction_data['status'] != 'active':
                print(f"Skipping inactive auction: {auction_id} (status: {auction_data['status']})")
                remove_active_auction(auction_id)
                continue

            # Check if auction is still active
            end_time = datetime.fromisoformat(auction_data['end_time'])

            if current_time < end_time:
                # Auction is still active - restore it and check for missed bids
                try:
                    thread = bot.get_channel(auction_data['thread_id'])
                    if thread:
                        # Check for missed bids in thread history
                        await process_missed_bids(bot, auction_id, auction_data, thread, end_time)

                        # Get updated auction data after processing missed bids
                        updated_auction = get_active_auction(auction_id)
                        if updated_auction:
                            auction_data = updated_auction

                        # Refresh the thread title to show current bid
                        try:
                            thread_prefix = "🧪" if auction_data.get('is_test', False) else "🚗"
                            current_title = f"{thread_prefix} {auction_data['car_name']} - ${auction_data['highest_bid']:,}"
                            await thread.edit(name=current_title)
                            print(f"Restored auction thread title: {current_title}")
                        except Exception as title_error:
                            print(f"Could not update thread title for auction {auction_id}: {title_error}")

                        # Post a restoration notice to let users know bidding is active again
                        try:
                            restore_embed = discord.Embed(
                                title="🔄 Auction Restored",
                                description=f"**{auction_data['car_name']}** auction is now active again!\n\n**Current Highest Bid:** ${auction_data['highest_bid']:,}\n\nYou can continue placing bids by sending amounts in this thread.",
                                color=discord.Color.blue()
                            )
                            restore_embed.add_field(
                                name="Auction Ends",
                                value=f"<t:{int(end_time.timestamp())}:R>",
                                inline=True
                            )
                            restore_embed.set_footer(text="Bot restarted - auction functionality restored")

                            restore_msg = await thread.send(embed=restore_embed)

                            # Auto-delete the restoration message after 30 seconds to keep thread clean
                            asyncio.create_task(delete_after_delay(restore_msg, 30))

                        except Exception as msg_error:
                            print(f"Could not send restoration message for auction {auction_id}: {msg_error}")
                    else:
                        print(f"Auction thread {auction_data['thread_id']} not found, cleaning up auction {auction_id}")
                        remove_active_auction(auction_id)
                        expired_count += 1
                        continue

                except Exception as thread_error:
                    print(f"Error accessing auction thread for {auction_id}: {thread_error}")
                    remove_active_auction(auction_id)
                    expired_count += 1
                    continue

                # Schedule the auction end with corrected remaining time
                remaining_time = (end_time - current_time).total_seconds()
                if remaining_time > 0:
                    asyncio.create_task(end_auction_timer(bot, auction_id, remaining_time))

                    # Schedule ending soon warning
                    is_test = auction_data.get('is_test', False)
                    warning_delay = remaining_time - (60 if is_test else 300)
                    if warning_delay > 0:
                        asyncio.create_task(auction_ending_soon_warning(bot, auction_id, warning_delay))

                    loaded_count += 1
                    print(f"Restored auction: {auction_data['car_name']} (ends in {remaining_time/3600:.1f} hours)")
                else:
                    # Auction should have ended, process missed bids first then end it
                    print(f"Processing auction that ended while bot was offline: {auction_id}")
                    thread = bot.get_channel(auction_data['thread_id'])
                    if thread:
                        await process_missed_bids(bot, auction_id, auction_data, thread, end_time)
                    asyncio.create_task(end_auction(bot, auction_id))
                    expired_count += 1
            else:
                # Auction has already ended while bot was offline - process missed bids then end it
                print(f"Processing auction that ended while bot was offline: {auction_id}")
                if auction_data['status'] == 'active':
                    thread = bot.get_channel(auction_data['thread_id'])
                    if thread:
                        await process_missed_bids(bot, auction_id, auction_data, thread, end_time)
                    asyncio.create_task(end_auction(bot, auction_id))
                else:
                    # Auction was already processed, just clean up
                    remove_active_auction(auction_id)
                expired_count += 1

        except Exception as e:
            print(f"Error processing auction {auction_id}: {e}")
            try:
                remove_active_auction(auction_id)
            except Exception:
                pass
            expired_count += 1

    print(f"Loaded {loaded_count} active auctions from database, processed {expired_count} expired ones")

def setup_persistent_auction_confirmation_views(bot):
    """Add persistent auction confirmation views to the bot"""
    # Get all active auctions that might have pending confirmations
    try:
        all_auctions = get_all_active_auctions()
        restored_count = 0
        
        for auction_id, auction_data in all_auctions.items():
            # Only restore views for auctions that have ended and are waiting for seller decision
            if auction_data.get('status') == 'ended' and auction_data.get('highest_bidder'):
                view = AuctionConfirmationView(auction_id)
                bot.add_view(view)
                restored_count += 1
                print(f"Restored auction confirmation view for auction {auction_id}")
        
        if restored_count > 0:
            print(f"Restored {restored_count} auction confirmation views")
    except Exception as e:
        print(f"Error restoring auction confirmation views: {e}")

def setup_auction_commands(tree):
    """Setup auction commands"""
    @tree.command(name="auction", description="Create a car auction listing.")
    @app_commands.describe(test="Create a test auction (Admin only, 1-10 minutes instead of 1-168 hours)")
    @app_commands.default_permissions(administrator=True)
    async def auction_command(interaction: Interaction, test: bool = False):
        if interaction.channel_id != AUCTION_CHANNEL_ID:
            await interaction.response.send_message(
                "This command can only be used in the #make-auction channel.",
                ephemeral=True
            )
            return

        # Check if test auction is requested and user has admin permissions
        if test and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Test auctions can only be created by administrators.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(AuctionModal(is_test=test))

    @tree.command(name="cancel-auction", description="Cancel your pending auction listing.")
    @app_commands.default_permissions(administrator=True)
    async def cancel_auction_command(interaction: Interaction):
        user_id = interaction.user.id

        # Check for both types of pending auction listings
        pending_regular = get_pending_listing(user_id, 'auction')
        pending_test = get_pending_listing(user_id, 'auction-test')

        if not pending_regular and not pending_test:
            await interaction.response.send_message(
                "You don't have any pending auction listings to cancel.",
                ephemeral=True
            )
            return

        # Remove the pending listing(s)
        if pending_regular:
            remove_pending_listing(user_id, 'auction')
        if pending_test:
            remove_pending_listing(user_id, 'auction-test')

        await interaction.response.send_message(
            "✅ Your pending auction listing has been cancelled. You can now create a new auction.",
            ephemeral=True
        )
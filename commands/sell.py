import discord
from discord.ui import Modal, TextInput, View, Button
from discord import app_commands, Interaction, TextStyle, ButtonStyle
import asyncio
from typing import Optional
from .utils import (
    format_price, listing_timeout, save_image_to_bot_channel,
    send_security_notice, private_channels_activity, log_channel_messages
)
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import improved modules
try:
    from config import config
    from logger_config import get_logger
    from validation import InputValidator, ValidationError
    from error_handler import handle_errors, ValidationError as BotValidationError
    logger = get_logger("sell")
except ImportError:
    # Fallback for backward compatibility
    SELL_CHANNEL_ID = config.SELL_CHANNEL_ID
SELL_TRADE_CHANNEL_ID = config.SELL_TRADE_CHANNEL_ID
    class config:
        SELL_CHANNEL_ID = SELL_CHANNEL_ID
        SELL_TRADE_CHANNEL_ID = SELL_TRADE_CHANNEL_ID
        MAX_USER_LISTINGS = 3
    def handle_errors(func): return func
    def log_info(msg): print(msg)
    def log_error(msg, exc_info=False): print(f"ERROR: {msg}")
    class InputValidator:
        @staticmethod
        def validate_price(price): return type('obj', (object,), {'is_valid': True, 'value': int(price.replace('$','').replace(',',''))})()
        @staticmethod  
        def validate_car_name(name): return type('obj', (object,), {'is_valid': True, 'value': name})()

from database_mysql import (
    get_user_listings, add_user_listing, add_active_deal, 
    get_pending_listing, add_pending_listing, remove_pending_listing,
    resolve_car_shortcode
)
from .car_disambiguation import handle_car_disambiguation

# Pending listings are now handled by the database

class MakeOfferModal(Modal, title='Make an Offer'):
    offered_price = TextInput(
        label='Offered Price',
        placeholder='e.g., 35000',
        style=TextStyle.short,
        required=True,
        max_length=20
    )

    def __init__(self, seller_id: int, car_name: str, listing_message_id: int):
        super().__init__()
        self.seller_id = seller_id
        self.car_name = car_name
        self.listing_message_id = listing_message_id

    async def on_submit(self, interaction: Interaction):
        try:
            # Validate offered price using new validation system
            price_validation = InputValidator.validate_price(self.offered_price.value)
            if not price_validation.is_valid:
                await interaction.response.send_message(
                    f"❌ {price_validation.error_message}",
                    ephemeral=True
                )
                return
            
            offered_price = price_validation.value

            # Format price
            formatted_price = format_price(str(offered_price))
            
            # Send confirmation to offer maker
            await interaction.response.send_message(
                f"Your offer of **{formatted_price}** for **{self.car_name}** has been sent to the seller!",
                ephemeral=True
            )

            # Create offer acceptance view
            offer_view = OfferResponseView(
                seller_id=self.seller_id,
                buyer_id=interaction.user.id,
                car_name=self.car_name,
                offered_price=formatted_price,
                listing_message_id=self.listing_message_id
            )

            # Send DM to seller
            try:
                seller = await interaction.client.fetch_user(self.seller_id)
                offer_embed = discord.Embed(
                    title="💰 New Offer Received",
                    description=f"**Car:** {self.car_name}\n**Offered Price:** {formatted_price}\n**From:** {interaction.user.mention} ({interaction.user.display_name})",
                    color=discord.Color.gold()
                )
                offer_embed.add_field(
                    name="Actions",
                    value="Use the buttons below to accept or reject this offer.",
                    inline=False
                )
                
                await seller.send(embed=offer_embed, view=offer_view)
                print(f"Sent offer DM to seller {seller.display_name} for {self.car_name}")

            except discord.Forbidden:
                # If can't send DM, send to channel
                await interaction.followup.send(
                    f"⚠️ Could not send DM to seller. Please contact them directly about your offer.",
                    ephemeral=True
                )
            except Exception as e:
                print(f"Error sending offer DM: {e}")
                await interaction.followup.send(
                    f"⚠️ Error sending offer to seller. Please try again.",
                    ephemeral=True
                )

        except Exception as e:
            print(f"Error in offer modal submission: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("An error occurred while processing your offer. Please try again.", ephemeral=True)
                else:
                    await interaction.followup.send("An error occurred while processing your offer. Please try again.", ephemeral=True)
            except:
                pass

class OfferResponseView(discord.ui.View):
    """View for seller to accept or reject offers via DM"""
    
    def __init__(self, seller_id: int, buyer_id: int, car_name: str, offered_price: str, listing_message_id: int):
        super().__init__(timeout=None)  # No timeout for persistent views
        self.seller_id = seller_id
        self.buyer_id = buyer_id
        self.car_name = car_name
        self.offered_price = offered_price
        self.listing_message_id = listing_message_id

        # Accept button
        accept_button = discord.ui.Button(
            label='✅ Accept Offer',
            style=discord.ButtonStyle.green,
            custom_id=f'accept_offer_{self.buyer_id}_{self.listing_message_id}'
        )
        accept_button.callback = self.accept_callback
        self.add_item(accept_button)

        # Reject button
        reject_button = discord.ui.Button(
            label='❌ Reject Offer',
            style=discord.ButtonStyle.red,
            custom_id=f'reject_offer_{self.buyer_id}_{self.listing_message_id}'
        )
        reject_button.callback = self.reject_callback
        self.add_item(reject_button)

    async def accept_callback(self, interaction: discord.Interaction):
        """Handle offer acceptance"""
        try:
            if interaction.user.id != self.seller_id:
                await interaction.response.send_message(
                    "Only the seller can accept or reject this offer.",
                    ephemeral=True
                )
                return

            # Disable buttons
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(view=self)

            # Get buyer user
            buyer = await interaction.client.fetch_user(self.buyer_id)
            
            # Send acceptance DM to buyer
            accept_embed = discord.Embed(
                title="✅ Offer Accepted!",
                description=f"**Car:** {self.car_name}\n**Your Offer:** {self.offered_price}\n**Seller:** {interaction.user.mention} ({interaction.user.display_name})",
                color=discord.Color.green()
            )
            accept_embed.add_field(
                name="Next Step",
                value="A private deal channel will be created for you to complete the transaction.",
                inline=False
            )

            # Create private channel for the deal
            guild = None
            # Find a guild where both users are members
            for g in interaction.client.guilds:
                if g.get_member(self.seller_id) and g.get_member(self.buyer_id):
                    guild = g
                    break

            if not guild:
                await buyer.send(embed=accept_embed)
                await interaction.followup.send("Could not create deal channel - users not in same server.", ephemeral=True)
                return

            member_role = guild.get_role(config.MEMBER_ROLE_ID)  # Member role
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
                buyer: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True, attach_files=True, embed_links=True)
            }

            if member_role:
                overwrites[member_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)

            channel = await guild.create_text_channel(
                name=f'offer-deal-{buyer.name}-{interaction.user.name}',
                overwrites=overwrites,
                topic=f'Private car sale (offer accepted) between {buyer.display_name} and {interaction.user.display_name}'
            )

            # Track channel activity and deal
            private_channels_activity[channel.id] = asyncio.get_event_loop().time()
            add_active_deal(
                channel.id,
                self.seller_id,
                self.buyer_id,
                self.car_name,
                self.listing_message_id
            )

            # Update acceptance embed with channel link
            accept_embed.add_field(
                name="Deal Channel",
                value=f"Click here to proceed: {channel.mention}",
                inline=False
            )

            # Send DMs with channel link
            try:
                await buyer.send(embed=accept_embed)
            except discord.Forbidden:
                pass

            seller_embed = discord.Embed(
                title="✅ Offer Accepted",
                description=f"You accepted the offer of **{self.offered_price}** for **{self.car_name}**.",
                color=discord.Color.green()
            )
            seller_embed.add_field(
                name="Deal Channel",
                value=f"Complete the transaction here: {channel.mention}",
                inline=False
            )

            await interaction.followup.send(embed=seller_embed, ephemeral=True)

            # Send initial message in deal channel
            initial_embed = discord.Embed(
                title="💰 Offer Deal Transaction",
                description=f"**Buyer:** {buyer.mention}\n**Seller:** {interaction.user.mention}\n\n🚗 **Car:** {self.car_name}\n💰 **Agreed Price:** {self.offered_price}\n📄 **Original Listing ID:** {self.listing_message_id}\n\nPlease complete your transaction here. Remember to exchange in-game IDs only!",
                color=discord.Color.gold()
            )
            
            view = DealChannelView(channel.id, self.seller_id, self.buyer_id, self.car_name)
            await channel.send(embed=initial_embed, view=view)
            await send_security_notice(channel)

        except Exception as e:
            print(f"Error accepting offer: {e}")
            try:
                await interaction.followup.send("Error processing offer acceptance.", ephemeral=True)
            except:
                pass

    async def reject_callback(self, interaction: discord.Interaction):
        """Handle offer rejection"""
        try:
            if interaction.user.id != self.seller_id:
                await interaction.response.send_message(
                    "Only the seller can accept or reject this offer.",
                    ephemeral=True
                )
                return

            # Disable buttons
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(view=self)

            # Get buyer user
            buyer = await interaction.client.fetch_user(self.buyer_id)
            
            # Send rejection DM to buyer
            reject_embed = discord.Embed(
                title="❌ Offer Rejected",
                description=f"**Car:** {self.car_name}\n**Your Offer:** {self.offered_price}\n**Seller:** {interaction.user.mention} ({interaction.user.display_name})",
                color=discord.Color.red()
            )
            reject_embed.add_field(
                name="What's Next?",
                value="You can make a new offer or try contacting the seller directly.",
                inline=False
            )

            try:
                await buyer.send(embed=reject_embed)
            except discord.Forbidden:
                pass

            # Send confirmation to seller
            await interaction.followup.send(f"You rejected the offer of **{self.offered_price}** for **{self.car_name}**.", ephemeral=True)

        except Exception as e:
            print(f"Error rejecting offer: {e}")
            try:
                await interaction.followup.send("Error processing offer rejection.", ephemeral=True)
            except:
                pass

class DealChannelView(discord.ui.View):
    """View for deal channel buttons"""
    
    def __init__(self, channel_id: int, seller_id: int, buyer_id: int, car_name: str):
        super().__init__(timeout=None)  # Persistent view
        self.channel_id = channel_id
        self.seller_id = seller_id
        self.buyer_id = buyer_id
        self.car_name = car_name
        
        # Complete deal button
        complete_button = discord.ui.Button(
            label='✅ Complete Deal',
            style=discord.ButtonStyle.green,
            custom_id=f'complete_deal_{channel_id}'
        )
        complete_button.callback = self.complete_callback
        self.add_item(complete_button)
        
        # Cancel deal button
        cancel_button = discord.ui.Button(
            label='❌ Cancel Deal',
            style=discord.ButtonStyle.red,
            custom_id=f'cancel_deal_{channel_id}'
        )
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)
    
    async def complete_callback(self, interaction: discord.Interaction):
        """Handle complete deal button - same as /close command"""
        try:
            # Import the deal confirmation function
            from .deal_confirmation import DealConfirmationView
            from database_mysql import add_deal_confirmation, get_deal_confirmation
            
            channel_id = interaction.channel.id
            
            # Check if deal confirmation already exists
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
            try:
                await interaction.response.edit_message(view=self)
            except:
                # If edit fails, just respond normally
                await interaction.response.defer()
            
            # Check if it's a giveaway claim channel
            is_giveaway_claim = (interaction.channel.name.startswith('giveaway-claim-') or 
                               interaction.channel.name.startswith('admin-giveaway-claim-'))
            
            # Initialize deal confirmation in database
            add_deal_confirmation(channel_id)
            
            # Create confirmation embed
            seller_label = "Host" if is_giveaway_claim else "Seller"
            buyer_label = "Winner" if is_giveaway_claim else "Buyer"
            deal_type = "Giveaway Prize" if is_giveaway_claim else "Car"
            
            try:
                seller = await interaction.client.fetch_user(self.seller_id)
                buyer = await interaction.client.fetch_user(self.buyer_id)
            except:
                await interaction.followup.send("Error: Could not fetch user information.", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🤝 Confirm Deal" if not is_giveaway_claim else "🎁 Confirm Prize Delivery",
                description=f"**{deal_type}:** {self.car_name}\n**{seller_label}:** {seller.mention}\n**{buyer_label}:** {buyer.mention}\n\nBoth parties need to confirm this {'deal' if not is_giveaway_claim else 'prize delivery'} was completed successfully.",
                color=discord.Color.blue() if not is_giveaway_claim else discord.Color.purple()
            )
            
            embed.add_field(
                name="Confirmation Status", 
                value=f"⏳ {buyer.mention} pending\n⏳ {seller.mention} pending", 
                inline=False
            )
            
            # Create confirmation view
            view = DealConfirmationView(
                channel_id=channel_id,
                seller_id=self.seller_id,
                buyer_id=self.buyer_id,
                car_name=self.car_name,
                is_giveaway_claim=is_giveaway_claim
            )
            
            await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            print(f"Error handling complete deal: {e}")
            try:
                await interaction.followup.send("Error starting deal confirmation.", ephemeral=True)
            except:
                pass
    
    async def cancel_callback(self, interaction: discord.Interaction):
        """Handle cancel deal button - same as /cancel command"""
        try:
            # Disable all buttons immediately to prevent multiple clicks
            for item in self.children:
                item.disabled = True
            
            # Update the message with disabled buttons and defer
            await interaction.response.edit_message(view=self)
            
            # Send cancellation message
            cancel_embed = discord.Embed(
                title="❌ Deal Cancelled",
                description=f"The deal for **{self.car_name}** has been cancelled.\n\n⏳ Channel will be deleted in 10 seconds.",
                color=discord.Color.red()
            )
            
            await interaction.followup.send(embed=cancel_embed, ephemeral=False)
            
            # Clean up
            from database_mysql import remove_active_deal, remove_deal_confirmation
            remove_active_deal(self.channel_id)
            remove_deal_confirmation(self.channel_id)
            if self.channel_id in private_channels_activity:
                del private_channels_activity[self.channel_id]
            
            # Schedule channel deletion
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
            print(f"Error handling cancel deal: {e}")
            try:
                await interaction.followup.send("Error cancelling deal.", ephemeral=True)
            except:
                pass

class SellModal(Modal, title='Create Sell Listing'):
    car_name = TextInput(
        label='Car Name',
        placeholder='e.g., BMW M5',
        style=TextStyle.short,
        required=True,
        max_length=100
    )
    extra_info = TextInput(
        label='Extra Informations (Optional)',
        placeholder='e.g., BodyKit, Custom Design, Badges, etc.',
        style=TextStyle.paragraph,
        required=False,
        max_length=300
    )
    price = TextInput(
        label='Price',
        placeholder='e.g., $40,000',
        style=TextStyle.short,
        required=True,
        max_length=50
    )

    async def on_submit(self, interaction: Interaction):
        user_id = interaction.user.id

        # Check if user already has a pending listing
        if get_pending_listing(user_id, 'sell'):
            await interaction.response.send_message(
                "You already have a pending sell listing awaiting an image. Please finish or cancel that one first.",
                ephemeral=True
            )
            return

        # Check if user has reached the maximum number of listings
        user_listings = get_user_listings(user_id)
        if len(user_listings) >= 3:
            await interaction.response.send_message(
                "You have reached the maximum number of active listings (3). Please delete an existing listing before creating a new one.",
                ephemeral=True
            )
            return

        # Resolve car shortcode
        from database_mysql import resolve_car_shortcode
        display_name, original_input, matches = resolve_car_shortcode(self.car_name.value)

        # Always respond to the interaction first to prevent timeout
        embed = discord.Embed(
            title="🚗 Sell Listing Started",
            description=f"**Car:** {display_name}\n"
                       f"**Price:** {self.price.value}\n\n"
                       f"Now upload an image of your car in this channel to complete your listing.\n\n"
                       f"⏰ You have 90 seconds to upload the image.",
            color=discord.Color.green()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Handle car disambiguation after responding
        async def proceed_with_sell(interaction_or_response, selected_car_name):
            # Store the listing as pending
            listing_data = {
                'car_name': selected_car_name,
                'extra_info': self.extra_info.value,
                'price': self.price.value,
                'channel_id': interaction.channel_id
            }
            add_pending_listing(interaction.user.id, 'sell', listing_data, interaction.channel_id)

            # Start timeout task
            timeout_task = asyncio.create_task(
                listing_timeout(interaction.user.id, interaction.channel, 'sell')
            )

            # Send followup with updated car name if different
            if selected_car_name != display_name:
                update_embed = discord.Embed(
                    title="🚗 Car Selection Updated",
                    description=f"**Selected Car:** {selected_car_name}\n"
                               f"**Price:** {self.price.value}\n\n"
                               f"Please upload your car image now.",
                    color=discord.Color.green()
                )
                await interaction_or_response.followup.send(embed=update_embed, ephemeral=True)

        # Check if disambiguation is needed
        if len(matches) > 1:
            # Multiple matches - show disambiguation menu after responding
            await handle_car_disambiguation(interaction, self.car_name.value, interaction.user.id, proceed_with_sell)
        else:
            # Single match or no matches - store the listing data
            listing_data = {
                'car_name': display_name,  # Use resolved display name
                'original_input': original_input,  # Store original input
                'extra_info': self.extra_info.value,
                'price': self.price.value,
                'channel_id': interaction.channel_id
            }
            add_pending_listing(interaction.user.id, 'sell', listing_data, interaction.channel_id)

            timeout_task = asyncio.create_task(
                listing_timeout(interaction.user.id, interaction.channel, 'sell')
            )

async def handle_sell_image_upload(bot, message):
    """Handle image upload for sell listings"""
    user_id = message.author.id

    try:
        pending_listing = get_pending_listing(user_id, 'sell')

        if not pending_listing:
            return False

        if not message.attachments:
            return False

        attachment = message.attachments[0]
        if not attachment.content_type or not attachment.content_type.startswith('image/'):
            await message.channel.send(f"{message.author.mention}, please upload a valid image file.", delete_after=10)
            await message.delete()
            return True

        print(f"Processing sell image upload for user {user_id}, car: {pending_listing.get('car_name', 'Unknown')}")

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
            remove_pending_listing(user_id, 'sell')
            if 'timeout_task' in pending_listing:
                pending_listing['timeout_task'].cancel()

            car_name = pending_listing['car_name']
            extra_info = pending_listing['extra_info']
            price = pending_listing['price']

            try:
                # Save the image to the bot channel
                saved_image_url = await save_image_to_bot_channel(
                    bot, image_url, "sell", car_name, message.author.display_name
                )
                print(f"Saved sell image to bot channel: {saved_image_url}")

                # Format the price
                formatted_price = format_price(price)

                # Create the final embed for the listing
                description = f"💰 **{formatted_price}**"
                if extra_info and extra_info.strip():
                    description += f"\n\n📋 **Extra Info:** {extra_info}"

                embed = discord.Embed(
                    title=f'🚗 **{car_name.upper()}**',
                    description=description,
                    color=discord.Color.green()
                )
                embed.set_image(url=saved_image_url)
                # Get user's trader role for display
                try:
                    from .trader_roles import get_user_trader_role_info
                    role_info = await get_user_trader_role_info(bot, user_id)
                    if role_info:
                        footer_text = f'Listed by {message.author.display_name} • {role_info["role_name"]}'
                    else:
                        footer_text = f'Listed by {message.author.display_name} • No Trader Role'
                except Exception as e:
                    print(f"Error getting trader role for embed: {e}")
                    footer_text = f'Listed by {message.author.display_name}'

                embed.set_footer(text=footer_text, icon_url=message.author.avatar.url if message.author.avatar else None)
                embed.timestamp = discord.utils.utcnow()

                # Create a view with buy button and offer button
                view = discord.ui.View()
                buy_button = discord.ui.Button(label='Buy Car', style=ButtonStyle.green, custom_id=f'buy_car_{user_id}')
                offer_button = discord.ui.Button(label='Make Offer', style=ButtonStyle.secondary, custom_id=f'make_offer_{user_id}')
                view.add_item(buy_button)
                view.add_item(offer_button)

                # Send the final listing message to the correct channel
                target_channel = message.channel
                if message.channel.id == SELL_TRADE_CHANNEL_ID:
                    # If listing was created from the sell/trade embed, send to sell channel
                    target_channel = message.guild.get_channel(SELL_CHANNEL_ID)
                    if not target_channel:
                        target_channel = message.channel  # Fallback to current channel

                listing_message = await target_channel.send(embed=embed, view=view)
                print(f"Created sell listing message for {car_name} in {target_channel.name}")

                # Store the message ID for the delete command
                add_user_listing(user_id, listing_message.id, car_name, 'sell')

                # Log the car price for market analysis
                try:
                    from database_mysql import log_car_price
                    log_car_price(car_name, price, user_id, message.author.display_name, listing_message.id)
                    print(f"Logged price for {car_name}: {price}")
                except Exception as e:
                    print(f"Error logging car price: {e}")

                # Process car recognition
                try:
                    from .car_recognition import process_car_listing
                    process_car_listing(car_name, 'sell', user_id, listing_message.id)
                except Exception as e:
                    print(f"Car recognition error: {e}")

                # Delete the user's original image upload message
                try:
                    await message.delete()
                    print(f"Deleted user's image upload from {message.author} in #{message.channel.name}.")
                except discord.HTTPException as e:
                    print(f"Failed to delete the user's image message: {e}")

                return True

            except Exception as e:
                print(f"Error processing sell listing: {e}")
                try:
                    await message.author.send(f"There was an error processing your sell listing: {str(e)}")
                except:
                    pass
                return True

        else:
            # If user uploaded something but it's not an image
            try:
                await message.delete()
                await message.author.send(
                    f"Your previous message in #{message.channel.name} has been deleted. "
                    "Please upload a **valid image file** (PNG, JPG, GIF, WEBP) to finalize the car listing."
                )
            except discord.HTTPException as e:
                print(f"Failed to handle non-image message: {e}")
            return True
    except Exception as e:
        print(f"Error in handle_sell_image_upload: {e}")
        return False

async def handle_make_offer_button(bot, interaction):
    """Handle make offer button interactions"""
    seller_user_id = int(interaction.data['custom_id'].split('_')[2])

    if interaction.user.id == seller_user_id:
        await interaction.response.send_message(
            "You cannot make an offer on your own car!",
            ephemeral=True
        )
        return

    # Extract car name and listing info from the embed
    car_name = "Unknown Car"
    listing_message_id = interaction.message.id

    if interaction.message.embeds:
        embed = interaction.message.embeds[0]
        if embed.title:
            car_name = embed.title.replace('🚗 **', '').replace('**', '').strip()

    # Show offer modal
    modal = MakeOfferModal(seller_user_id, car_name, listing_message_id)
    await interaction.response.send_modal(modal)

async def handle_buy_button(bot, interaction):
    """Handle buy button interactions"""
    seller_user_id = int(interaction.data['custom_id'].split('_')[2])

    if interaction.user.id == seller_user_id:
        await interaction.response.send_message(
            "You cannot buy your own car!",
            ephemeral=True
        )
        return

    try:
        seller = await bot.fetch_user(seller_user_id)
    except discord.NotFound:
        await interaction.response.send_message(
            "Could not find the seller.",
            ephemeral=True
        )
        return

    # Extract car name and listing info from the embed
    car_name = "Unknown Car"
    listing_message_id = interaction.message.id

    if interaction.message.embeds:
        embed = interaction.message.embeds[0]
        if embed.title:
            car_name = embed.title.replace('🚗 **', '').replace('**', '').strip()

    # Create a private channel for the transaction
    guild = interaction.guild
            member_role = guild.get_role(config.MEMBER_ROLE_ID)  # Member role
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        seller: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True, attach_files=True, embed_links=True)
    }

    # Add member role permissions if it exists
    if member_role:
        overwrites[member_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)

    try:
        channel = await guild.create_text_channel(
            name=f'car-sale-{interaction.user.name}-{seller.name}',
            overwrites=overwrites,
            topic=f'Private car sale between {interaction.user.display_name} and {seller.display_name}'
        )

        # Track channel activity
        private_channels_activity[channel.id] = asyncio.get_event_loop().time()

        # Track the deal for sales confirmation
        add_active_deal(
            channel.id,
            seller_user_id,
            interaction.user.id,
            car_name,
            listing_message_id
        )

        await interaction.response.send_message(
            f"Private channel created: {channel.mention}",
            ephemeral=True
        )

        # Send initial messages in the private channel
        initial_embed = discord.Embed(
            title="🚗 Car Sale Transaction",
            description=f"**Buyer:** {interaction.user.mention}\n**Seller:** {seller.mention}\n\n🚗 **This deal is about:** {car_name}\n📄 **Listing ID:** {listing_message_id}\n\nPlease complete your transaction here. Remember to exchange in-game IDs only!",
            color=discord.Color.green()
        )
        
        # Create view with deal buttons
        view = DealChannelView(channel.id, seller_user_id, interaction.user.id, car_name)
        await channel.send(embed=initial_embed, view=view)

        await send_security_notice(channel)

    except Exception as e:
        print(f"Error creating private channel: {e}")
        await interaction.response.send_message(
            f"Error creating private channel: {str(e)}",
            ephemeral=True
        )

def setup_persistent_offer_views(bot):
    """Setup persistent views for offer responses"""
    # Note: OfferResponseView instances are created dynamically when offers are made
    # No need to add placeholder persistent views as they are created on-demand
    print("Offer response views will be created dynamically when offers are made")

def setup_sell_command(tree):
    """Setup the sell command"""
    @tree.command(name="sell", description="List a car for sale")
    @app_commands.default_permissions(administrator=True)
    async def sell_command(interaction: Interaction):
        if interaction.channel_id not in [SELL_CHANNEL_ID, SELL_TRADE_CHANNEL_ID]:
            await interaction.response.send_message(
                "This command can only be used in the #sell-cars or #make-sell-trade channels.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(SellModal())
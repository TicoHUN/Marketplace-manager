import discord
from discord.ui import Modal, TextInput, View, Button
from discord import app_commands, Interaction, TextStyle, ButtonStyle
import asyncio
from config import config
from .utils import (
    listing_timeout, save_image_to_bot_channel,
    send_security_notice, private_channels_activity
)

from database_mysql import (
    add_user_listing, get_pending_listing, add_pending_listing,
    remove_pending_listing, add_active_deal, resolve_car_shortcode
)
from .car_disambiguation import handle_car_disambiguation

# Channel IDs
TRADE_CHANNEL_ID = config.TRADE_CHANNEL_ID # ID for #trade-cars channel
SELL_TRADE_CHANNEL_ID = config.SELL_TRADE_CHANNEL_ID  # ID for #make-sell-trade channel

# Pending listings are now handled by the database

class TradeModal(Modal, title='Create Trade Listing'):
    car_name = TextInput(
        label='Your Car Name',
        placeholder='e.g., Mercedes C63 AMG',
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
    trade_for = TextInput(
        label='Looking to trade for',
        placeholder='e.g., Porsche 911 or similar sports car',
        style=TextStyle.paragraph,
        required=True,
        max_length=250
    )

    async def on_submit(self, interaction: Interaction):
        try:
            print(f"TradeModal submitted by {interaction.user.id}")

            # Get user inputs
            user_car = self.car_name.value.strip()
            user_description = self.extra_info.value.strip() if self.extra_info.value else ""
            trade_for = self.trade_for.value.strip()

            if not user_car:
                await interaction.response.send_message("Please enter your car name.", ephemeral=True)
                return

            print(f"Trade request: {user_car} for {trade_for}")

            user_id = interaction.user.id

            # Check if user already has a pending listing
            if get_pending_listing(user_id, 'trade'):
                await interaction.response.send_message(
                    "You already have a pending trade listing awaiting an image. Please finish or cancel that one first.",
                    ephemeral=True
                )
                return

            # Check if user has reached the maximum number of listings
            from database_mysql import get_user_listings
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
                title="🔄 Trade Listing Started",
                description=f"**Car:** {display_name}\n"
                           f"**Looking for:** {self.trade_for.value}\n\n"
                           f"Now upload an image of your car in this channel to complete your listing.\n\n"
                           f"⏰ You have 90 seconds to upload the image.",
                color=discord.Color.blue()
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

            # Handle car disambiguation after responding
            async def proceed_with_trade(interaction_or_response, selected_car_name):
                # Store the listing as pending
                listing_data = {
                    'car_name': selected_car_name,
                    'extra_info': self.extra_info.value,
                    'trade_for': self.trade_for.value,
                    'channel_id': interaction.channel_id
                }
                add_pending_listing(user_id, 'trade', listing_data, interaction.channel_id)

                # Start timeout task
                timeout_task = asyncio.create_task(
                    listing_timeout(user_id, interaction.channel, 'trade')
                )

                # Send followup with updated car name if different
                if selected_car_name != display_name:
                    update_embed = discord.Embed(
                        title="🔄 Car Selection Updated",
                        description=f"**Selected Car:** {selected_car_name}\n"
                                   f"**Looking for:** {self.trade_for.value}\n\n"
                                   f"Please upload your car image now.",
                        color=discord.Color.blue()
                    )
                    await interaction_or_response.followup.send(embed=update_embed, ephemeral=True)

            # Check if disambiguation is needed
            if len(matches) > 1:
                # Multiple matches - show disambiguation menu after responding
                await handle_car_disambiguation(interaction, self.car_name.value, user_id, proceed_with_trade)
            else:
                # Single match or no matches - store the listing data
                listing_data = {
                    'car_name': display_name,  # Use resolved display name
                    'original_input': original_input,  # Store original input
                    'extra_info': self.extra_info.value,
                    'trade_for': self.trade_for.value,
                    'channel_id': interaction.channel_id
                }
                add_pending_listing(user_id, 'trade', listing_data, interaction.channel_id)

                timeout_task = asyncio.create_task(
                    listing_timeout(user_id, interaction.channel, 'trade')
                )

        except Exception as e:
            print(f"Error in trade modal submission: {e}")
            import traceback
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("An error occurred while processing your trade request. Please try again.", ephemeral=True)
                else:
                    await interaction.followup.send("An error occurred while processing your trade request. Please try again.", ephemeral=True)
            except Exception as followup_error:
                print(f"Error sending error message: {followup_error}")

async def handle_trade_image_upload(bot, message):
    """Handle image upload for trade listings"""
    user_id = message.author.id

    listing_data = get_pending_listing(user_id, 'trade')
    if not listing_data:
        return False

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
        remove_pending_listing(user_id, 'trade')
        if 'timeout_task' in listing_data:
            listing_data['timeout_task'].cancel()

        car_name = listing_data['car_name']
        extra_info = listing_data['extra_info']
        trade_for = listing_data['trade_for']

        try:
            # Save the image to the bot channel
            saved_image_url = await save_image_to_bot_channel(
                bot, image_url, "trade", car_name, message.author.display_name
            )
            print(f"Saved trade image to bot channel: {saved_image_url}")

            # Create the final embed for the trade listing
            description = f"🔄 **Looking for:** {trade_for}"
            if extra_info and extra_info.strip():
                description += f"\n\n📋 **Extra Info:** {extra_info}"

            embed = discord.Embed(
                title=f'🔄 **{car_name.upper()}**',
                description=description,
                color=discord.Color.blue()
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

            # Create a view with trade button and offer button
            view = discord.ui.View()
            trade_button = discord.ui.Button(label='Trade Car', style=ButtonStyle.primary, custom_id=f'trade_car_{user_id}')
            offer_button = discord.ui.Button(label='Make Offer', style=ButtonStyle.secondary, custom_id=f'make_trade_offer_{user_id}')
            view.add_item(trade_button)
            view.add_item(offer_button)

            # Send the final listing message to the correct channel
            target_channel = message.channel
            if message.channel.id == SELL_TRADE_CHANNEL_ID:
                # If listing was created from the sell/trade embed, send to trade channel
                target_channel = message.guild.get_channel(TRADE_CHANNEL_ID)
                if not target_channel:
                    target_channel = message.channel  # Fallback to current channel

            listing_message = await target_channel.send(embed=embed, view=view)
            print(f"Created trade listing message for {car_name} in {target_channel.name}")

            # Store the message ID for the delete command
            from database_mysql import add_user_listing
            add_user_listing(user_id, listing_message.id, car_name, 'trade')

            # Process car recognition
            try:
                from .car_recognition import process_car_listing
                process_car_listing(car_name, 'trade', user_id, listing_message.id)
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
            print(f"Error processing trade listing: {e}")
            try:
                await message.author.send(f"There was an error processing your trade listing: {str(e)}")
            except:
                pass
            return True

    else:
        # If user uploaded something but it's not an image
        try:
            await message.delete()
            await message.author.send(
                f"Your previous message in #{message.channel.name} has been deleted. "
                "Please upload a **valid image file** (PNG, JPG, GIF, WEBP) to finalize the car trade listing."
            )
        except discord.HTTPException as e:
            print(f"Failed to handle non-image message: {e}")
        return True

class MakeTradeOfferModal(Modal, title='Make a Trade Offer'):
    offered_car = TextInput(
        label='Your Car for Trade',
        placeholder='e.g., BMW M3, Porsche 911',
        style=TextStyle.short,
        required=True,
        max_length=100
    )

    def __init__(self, trader_id: int, car_name: str, listing_message_id: int):
        super().__init__()
        self.trader_id = trader_id
        self.car_name = car_name
        self.listing_message_id = listing_message_id

    async def on_submit(self, interaction: Interaction):
        try:
            offered_car = self.offered_car.value.strip()
            
            if not offered_car:
                await interaction.response.send_message(
                    "Please enter a car name for your trade offer!",
                    ephemeral=True
                )
                return

            # Send confirmation to offer maker
            await interaction.response.send_message(
                f"Your trade offer of **{offered_car}** for **{self.car_name}** has been sent to the trader!",
                ephemeral=True
            )

            # Create trade offer acceptance view
            trade_offer_view = TradeOfferResponseView(
                trader_id=self.trader_id,
                offeror_id=interaction.user.id,
                target_car=self.car_name,
                offered_car=offered_car,
                listing_message_id=self.listing_message_id
            )

            # Send DM to trader
            try:
                trader = await interaction.client.fetch_user(self.trader_id)
                offer_embed = discord.Embed(
                    title="🔄 New Trade Offer Received",
                    description=f"**Your Car:** {self.car_name}\n**Offered Car:** {offered_car}\n**From:** {interaction.user.mention} ({interaction.user.display_name})",
                    color=discord.Color.blue()
                )
                offer_embed.add_field(
                    name="Actions",
                    value="Use the buttons below to accept or reject this trade offer.",
                    inline=False
                )
                
                await trader.send(embed=offer_embed, view=trade_offer_view)
                print(f"Sent trade offer DM to trader {trader.display_name} for {self.car_name}")

            except discord.Forbidden:
                await interaction.followup.send(
                    f"⚠️ Could not send DM to trader. Please contact them directly about your offer.",
                    ephemeral=True
                )
            except Exception as e:
                print(f"Error sending trade offer DM: {e}")
                await interaction.followup.send(
                    f"⚠️ Error sending offer to trader. Please try again.",
                    ephemeral=True
                )

        except Exception as e:
            print(f"Error in trade offer modal submission: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("An error occurred while processing your trade offer. Please try again.", ephemeral=True)
                else:
                    await interaction.followup.send("An error occurred while processing your trade offer. Please try again.", ephemeral=True)
            except:
                pass

class TradeOfferResponseView(discord.ui.View):
    """View for trader to accept or reject trade offers via DM"""
    
    def __init__(self, trader_id: int, offeror_id: int, target_car: str, offered_car: str, listing_message_id: int):
        super().__init__(timeout=None)  # No timeout for persistent views
        self.trader_id = trader_id
        self.offeror_id = offeror_id
        self.target_car = target_car
        self.offered_car = offered_car
        self.listing_message_id = listing_message_id

        # Accept button
        accept_button = discord.ui.Button(
            label='✅ Accept Trade',
            style=discord.ButtonStyle.green,
            custom_id=f'accept_trade_offer_{self.offeror_id}_{self.listing_message_id}'
        )
        accept_button.callback = self.accept_callback
        self.add_item(accept_button)

        # Reject button
        reject_button = discord.ui.Button(
            label='❌ Reject Trade',
            style=discord.ButtonStyle.red,
            custom_id=f'reject_trade_offer_{self.offeror_id}_{self.listing_message_id}'
        )
        reject_button.callback = self.reject_callback
        self.add_item(reject_button)

    async def accept_callback(self, interaction: discord.Interaction):
        """Handle trade offer acceptance"""
        try:
            if interaction.user.id != self.trader_id:
                await interaction.response.send_message(
                    "Only the trader can accept or reject this offer.",
                    ephemeral=True
                )
                return

            # Disable buttons
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(view=self)

            # Get offeror user
            offeror = await interaction.client.fetch_user(self.offeror_id)
            
            # Send acceptance DM to offeror
            accept_embed = discord.Embed(
                title="✅ Trade Offer Accepted!",
                description=f"**Your Offer:** {self.offered_car}\n**For:** {self.target_car}\n**Trader:** {interaction.user.mention} ({interaction.user.display_name})",
                color=discord.Color.green()
            )
            accept_embed.add_field(
                name="Next Step",
                value="A private deal channel will be created for you to complete the trade.",
                inline=False
            )

            # Create private channel for the trade
            guild = None
            # Find a guild where both users are members
            for g in interaction.client.guilds:
                if g.get_member(self.trader_id) and g.get_member(self.offeror_id):
                    guild = g
                    break

            if not guild:
                await offeror.send(embed=accept_embed)
                await interaction.followup.send("Could not create deal channel - users not in same server.", ephemeral=True)
                return

            member_role = guild.get_role(config.MEMBER_ROLE_ID)  # Member role
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
                offeror: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True, attach_files=True, embed_links=True)
            }

            if member_role:
                overwrites[member_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)

            channel = await guild.create_text_channel(
                name=f'trade-offer-{offeror.name}-{interaction.user.name}',
                overwrites=overwrites,
                topic=f'Private car trade (offer accepted) between {offeror.display_name} and {interaction.user.display_name}'
            )

            # Track channel activity and deal
            private_channels_activity[channel.id] = asyncio.get_event_loop().time()
            add_active_deal(
                channel.id,
                self.trader_id,
                self.offeror_id,
                self.target_car,
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
                await offeror.send(embed=accept_embed)
            except discord.Forbidden:
                pass

            trader_embed = discord.Embed(
                title="✅ Trade Offer Accepted",
                description=f"You accepted the trade offer of **{self.offered_car}** for **{self.target_car}**.",
                color=discord.Color.green()
            )
            trader_embed.add_field(
                name="Deal Channel",
                value=f"Complete the trade here: {channel.mention}",
                inline=False
            )

            await interaction.followup.send(embed=trader_embed, ephemeral=True)

            # Send initial message in deal channel
            initial_embed = discord.Embed(
                title="🔄 Trade Offer Transaction",
                description=f"**Trader 1:** {offeror.mention}\n**Trader 2:** {interaction.user.mention}\n\n🚗 **Trade:** {self.offered_car} ↔ {self.target_car}\n📄 **Original Listing ID:** {self.listing_message_id}\n\nPlease complete your trade here. Remember to exchange in-game IDs only!",
                color=discord.Color.blue()
            )
            
            from .sell import DealChannelView
            view = DealChannelView(channel.id, self.trader_id, self.offeror_id, self.target_car)
            await channel.send(embed=initial_embed, view=view)
            await send_security_notice(channel)

        except Exception as e:
            print(f"Error accepting trade offer: {e}")
            try:
                await interaction.followup.send("Error processing trade offer acceptance.", ephemeral=True)
            except:
                pass

    async def reject_callback(self, interaction: discord.Interaction):
        """Handle trade offer rejection"""
        try:
            if interaction.user.id != self.trader_id:
                await interaction.response.send_message(
                    "Only the trader can accept or reject this offer.",
                    ephemeral=True
                )
                return

            # Disable buttons
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(view=self)

            # Get offeror user
            offeror = await interaction.client.fetch_user(self.offeror_id)
            
            # Send rejection DM to offeror
            reject_embed = discord.Embed(
                title="❌ Trade Offer Rejected",
                description=f"**Your Offer:** {self.offered_car}\n**For:** {self.target_car}\n**Trader:** {interaction.user.mention} ({interaction.user.display_name})",
                color=discord.Color.red()
            )
            reject_embed.add_field(
                name="What's Next?",
                value="You can make a new trade offer or try contacting the trader directly.",
                inline=False
            )

            try:
                await offeror.send(embed=reject_embed)
            except discord.Forbidden:
                pass

            # Send confirmation to trader
            await interaction.followup.send(f"You rejected the trade offer of **{self.offered_car}** for **{self.target_car}**.", ephemeral=True)

        except Exception as e:
            print(f"Error rejecting trade offer: {e}")
            try:
                await interaction.followup.send("Error processing trade offer rejection.", ephemeral=True)
            except:
                pass

async def handle_make_trade_offer_button(bot, interaction):
    """Handle make trade offer button interactions"""
    trader_user_id = int(interaction.data['custom_id'].split('_')[3])

    if interaction.user.id == trader_user_id:
        await interaction.response.send_message(
            "You cannot make a trade offer on your own car!",
            ephemeral=True
        )
        return

    # Extract car name and listing info from the embed
    car_name = "Unknown Car"
    listing_message_id = interaction.message.id

    if interaction.message.embeds:
        embed = interaction.message.embeds[0]
        if embed.title:
            car_name = embed.title.replace('🔄 **', '').replace('**', '').strip()

    # Show trade offer modal
    modal = MakeTradeOfferModal(trader_user_id, car_name, listing_message_id)
    await interaction.response.send_modal(modal)

def setup_persistent_trade_offer_views(bot):
    """Setup persistent views for trade offer responses"""
    # Note: TradeOfferResponseView instances are created dynamically when offers are made
    # No need to add placeholder persistent views as they are created on-demand
    print("Trade offer response views will be created dynamically when offers are made")

async def handle_trade_button(bot, interaction):
    """Handle trade button interactions"""
    trader_user_id = int(interaction.data['custom_id'].split('_')[2])

    if interaction.user.id == trader_user_id:
        await interaction.response.send_message(
            "You cannot trade with yourself!",
            ephemeral=True
        )
        return

    try:
        trader = await bot.fetch_user(trader_user_id)
    except discord.NotFound:
        await interaction.response.send_message(
            "Could not find the trader.",
            ephemeral=True
        )
        return

    # Extract car name and listing info from the embed
    car_name = "Unknown Car"
    listing_message_id = interaction.message.id

    if interaction.message.embeds:
        embed = interaction.message.embeds[0]
        if embed.title:
            car_name = embed.title.replace('🔄 **', '').replace('**', '').strip()

    # Create a private channel for the transaction
    guild = interaction.guild
    member_role = guild.get_role(config.MEMBER_ROLE_ID)  # Member role
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        trader: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True, attach_files=True, embed_links=True)
    }

    # Add member role permissions if it exists
    if member_role:
        overwrites[member_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)

    try:
        channel = await guild.create_text_channel(
            name=f'car-trade-{interaction.user.name}-{trader.name}',
            overwrites=overwrites,
            topic=f'Private car trade between {interaction.user.display_name} and {trader.display_name}'
        )

        # Track channel activity
        private_channels_activity[channel.id] = asyncio.get_event_loop().time()

        # Track the deal for trade confirmation
        add_active_deal(
            channel.id,
            trader_user_id,
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
            title="🔄 Car Trade Transaction",
            description=f"**Trader 1:** {interaction.user.mention}\n**Trader 2:** {trader.mention}\n\n🚗 **This deal is about:** {car_name}\n📄 **Listing ID:** {listing_message_id}\n\nPlease complete your trade here. Remember to exchange in-game IDs only!",
            color=discord.Color.blue()
        )

        # Create view with deal buttons  
        from .sell import DealChannelView
        view = DealChannelView(channel.id, trader_user_id, interaction.user.id, car_name)
        await channel.send(embed=initial_embed, view=view)

        await send_security_notice(channel)

    except Exception as e:
        print(f"Error creating private channel: {e}")
        await interaction.response.send_message(
            f"Error creating private channel: {str(e)}",
            ephemeral=True
        )

def setup_trade_command(tree):
    """Setup the trade command"""
    @tree.command(name="trade", description="List a car for trade")
    @app_commands.default_permissions(administrator=True)
    async def trade_command(interaction: Interaction):
        if interaction.channel_id not in [TRADE_CHANNEL_ID, SELL_TRADE_CHANNEL_ID]:
            await interaction.response.send_message(
                "This command can only be used in the #trade-cars or #make-sell-trade channels.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.send_modal(TradeModal())
            print(f"Trade modal sent successfully")
        except Exception as e:
            print(f"Error sending trade modal: {e}")
            await interaction.response.send_message(
                "There was an error opening the trade form. Please try again.",
                ephemeral=True
            )
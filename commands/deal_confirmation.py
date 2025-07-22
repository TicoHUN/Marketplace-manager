import discord
from discord.ext import commands
import asyncio

# Import database functions
from database_mysql import (
    get_deal_confirmation, update_deal_confirmation, remove_deal_confirmation,
    get_active_deal, remove_active_deal, record_sale, remove_user_listing,
    get_user_sales
)
from commands.utils import log_channel_messages, private_channels_activity
from commands.trader_roles import update_trader_role

class DealConfirmationView(discord.ui.View):
    """Persistent view for deal confirmation buttons"""

    def __init__(self, channel_id: int, seller_id: int, buyer_id: int, car_name: str, is_giveaway_claim: bool = False):
        super().__init__(timeout=None)  # Persistent view
        self.channel_id = channel_id
        self.seller_id = seller_id
        self.buyer_id = buyer_id
        self.car_name = car_name
        self.is_giveaway_claim = is_giveaway_claim

        # Create the confirm button with persistent custom_id
        self.confirm_button = discord.ui.Button(
            label='✅ Confirm Deal',
            style=discord.ButtonStyle.green,
            custom_id=f'confirm_deal_{channel_id}'
        )
        self.confirm_button.callback = self.confirm_callback
        self.add_item(self.confirm_button)
        
        # Create the scam report button
        self.scam_button = discord.ui.Button(
            label='🚨 I got scammed',
            style=discord.ButtonStyle.red,
            custom_id=f'scam_report_{channel_id}'
        )
        self.scam_button.callback = self.scam_callback
        self.add_item(self.scam_button)

    async def confirm_callback(self, interaction: discord.Interaction):
        """Handle button click with improved error handling"""
        user_id = interaction.user.id

        # Acknowledge the interaction immediately
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.errors.InteractionResponded:
            # Interaction already responded to, use followup
            pass
        except discord.errors.NotFound:
            # Interaction expired, send new message
            try:
                await interaction.channel.send("Interaction expired, please try the button again.", delete_after=5)
            except:
                pass
            return

        # Only allow seller and buyer to confirm
        if user_id not in [self.seller_id, self.buyer_id]:
            try:
                await interaction.followup.send(
                    "Only the buyer and seller can confirm this deal.",
                    ephemeral=True
                )
            except:
                pass
            return

        # Check if user has already confirmed
        confirmations = get_deal_confirmation(self.channel_id)
        if not confirmations:
            try:
                await interaction.followup.send(
                    "Deal confirmation data not found. Please try again.",
                    ephemeral=True
                )
            except:
                pass
            return

        # Check if user already confirmed
        if user_id == self.buyer_id and confirmations["buyer_confirmed"]:
            try:
                await interaction.followup.send(
                    "You have already confirmed this deal.",
                    ephemeral=True
                )
            except:
                pass
            return
        elif user_id == self.seller_id and confirmations["seller_confirmed"]:
            try:
                await interaction.followup.send(
                    "You have already confirmed this deal.",
                    ephemeral=True
                )
            except:
                pass
            return

        # Update confirmation status in database
        if user_id == self.buyer_id:
            update_deal_confirmation(self.channel_id, buyer_confirmed=True)
        elif user_id == self.seller_id:
            update_deal_confirmation(self.channel_id, seller_confirmed=True)

        # Get updated confirmations
        updated_confirmations = get_deal_confirmation(self.channel_id)

        # Fetch user objects
        try:
            seller = await interaction.client.fetch_user(self.seller_id)
            buyer = await interaction.client.fetch_user(self.buyer_id)
        except discord.NotFound:
            try:
                await interaction.followup.send(
                    "Error: Could not find user information.",
                    ephemeral=True
                )
            except:
                pass
            return

        # Check if both parties have confirmed
        if updated_confirmations["buyer_confirmed"] and updated_confirmations["seller_confirmed"]:
            # Both confirmed - complete the deal
            if self.is_giveaway_claim:
                completion_embed = discord.Embed(
                    title="🎁 Prize Delivered!",
                    description=f"**Prize:** {self.car_name}\n**Host:** {seller.mention}\n**Winner:** {buyer.mention}\n\nPrize delivery has been successfully completed!\n\n⏳ This channel will be deleted in 10 seconds.",
                    color=discord.Color.purple()
                )
            else:
                # Regular deal - record sale
                sales_count = record_sale(self.seller_id)
                completion_embed = discord.Embed(
                    title="✅ Deal Completed!",
                    description=f"**Car:** {self.car_name}\n**Seller:** {seller.mention}\n**Buyer:** {buyer.mention}\n\nDeal has been successfully completed and recorded!\n\n⏳ This channel will be deleted in 10 seconds.",
                    color=discord.Color.green()
                )
                completion_embed.add_field(
                    name="Sales Record", 
                    value=f"{seller.mention} now has **{sales_count}** completed sales!", 
                    inline=False
                )

                # Update trader role for seller based on new sales count
                try:
                    role_success, role_message = await update_trader_role(
                        interaction.client, self.seller_id, sales_count
                    )
                    if role_success and "Assigned" in role_message:
                        # Add role update notification to embed if a new role was assigned
                        completion_embed.add_field(
                            name="🏆 Role Update",
                            value=role_message,
                            inline=False
                        )
                    elif not role_success:
                        print(f"Failed to update trader role for user {self.seller_id}: {role_message}")
                except Exception as e:
                    print(f"Error updating trader role for user {self.seller_id}: {e}")

                # Also update trader role for buyer (they get credit for completing deals too)
                try:
                    buyer_new_count = record_sale(self.buyer_id)  # Record sale for buyer too

                    buyer_role_success, buyer_role_message = await update_trader_role(
                        interaction.client, self.buyer_id, buyer_new_count
                    )
                    if buyer_role_success and "Assigned" in buyer_role_message:
                        # Add buyer role update if they got a new role
                        completion_embed.add_field(
                            name="🏆 Buyer Role Update",
                            value=f"{buyer.mention}: {buyer_role_message}",
                            inline=False
                        )
                    elif not buyer_role_success:
                        print(f"Failed to update trader role for buyer {self.buyer_id}: {buyer_role_message}")
                except Exception as e:
                    print(f"Error updating trader role for buyer {self.buyer_id}: {e}")

            # Edit the original message with completion status
            try:
                # Find the original message with the confirmation embed
                async for message in interaction.channel.history(limit=50):
                    if (message.embeds and 
                        message.embeds[0].title in ["🤝 Confirm Deal", "🎁 Confirm Prize Delivery"] and
                        message.author == interaction.client.user):
                        await message.edit(embed=completion_embed, view=None)
                        break
                else:
                    # If original message not found, send new one
                    await interaction.channel.send(embed=completion_embed)
            except Exception as e:
                print(f"Error editing completion message: {e}")
                try:
                    await interaction.channel.send(embed=completion_embed)
                except:
                    pass

            # Send confirmation to user
            try:
                await interaction.followup.send("Deal confirmed successfully!", ephemeral=True)
            except:
                pass

            # Delete original listing if it exists
            deal_info = get_active_deal(self.channel_id)
            if deal_info and deal_info.get("listing_message_id"):
                try:
                    from main import SELL_CHANNEL_ID, TRADE_CHANNEL_ID

                    listing_channel = None
                    channel_name = interaction.channel.name
                    if channel_name.startswith('car-sale-'):
                        listing_channel = interaction.client.get_channel(SELL_CHANNEL_ID)
                    elif channel_name.startswith('car-trade-'):
                        listing_channel = interaction.client.get_channel(TRADE_CHANNEL_ID)

                    if listing_channel:
                        listing_message = await listing_channel.fetch_message(deal_info["listing_message_id"])
                        await listing_message.delete()
                        # Remove from user listings database
                        remove_user_listing(self.seller_id, deal_info["listing_message_id"])
                        print(f"Deleted original listing message for {self.car_name}")
                except discord.NotFound:
                    print(f"Original listing message not found for {self.car_name}")
                except Exception as e:
                    print(f"Error deleting original listing: {e}")

            # Clean up database and tracking
            remove_active_deal(self.channel_id)
            remove_deal_confirmation(self.channel_id)
            if self.channel_id in private_channels_activity:
                del private_channels_activity[self.channel_id]

            # Schedule channel deletion with logging
            async def delayed_deletion():
                await asyncio.sleep(10)
                try:
                    await log_channel_messages(interaction.client, interaction.channel)
                    await interaction.channel.delete(reason="Deal completed and confirmed by both parties")
                    print(f"Deleted completed deal channel: {interaction.channel.name}")
                except Exception as e:
                    print(f"Error deleting deal channel: {e}")

            asyncio.create_task(delayed_deletion())

        else:
            # One party confirmed, update the embed
            seller_label = "Host" if self.is_giveaway_claim else "Seller"
            buyer_label = "Winner" if self.is_giveaway_claim else "Buyer"
            deal_type = "Giveaway Prize" if self.is_giveaway_claim else "Car"

            updated_status = ""
            if updated_confirmations["buyer_confirmed"]:
                updated_status += f"✅ {buyer.mention} confirmed\n"
            else:
                updated_status += f"⏳ {buyer.mention} pending\n"

            if updated_confirmations["seller_confirmed"]:
                updated_status += f"✅ {seller.mention} confirmed\n"
            else:
                updated_status += f"⏳ {seller.mention} pending\n"

            updated_embed = discord.Embed(
                title="🤝 Confirm Deal" if not self.is_giveaway_claim else "🎁 Confirm Prize Delivery",
                description=f"**{deal_type}:** {self.car_name}\n**{seller_label}:** {seller.mention}\n**{buyer_label}:** {buyer.mention}\n\nBoth parties need to confirm this {'deal' if not self.is_giveaway_claim else 'prize delivery'} was completed successfully.",
                color=discord.Color.blue() if not self.is_giveaway_claim else discord.Color.purple()
            )
            updated_embed.add_field(name="Confirmation Status", value=updated_status, inline=False)

            # Find and edit the original message
            try:
                async for message in interaction.channel.history(limit=50):
                    if (message.embeds and 
                        message.embeds[0].title in ["🤝 Confirm Deal", "🎁 Confirm Prize Delivery"] and
                        message.author == interaction.client.user):
                        await message.edit(embed=updated_embed, view=self)
                        break
                else:
                    # If original message not found, send new one
                    await interaction.channel.send(embed=updated_embed, view=self)
            except Exception as e:
                print(f"Error editing updated message: {e}")
                try:
                    await interaction.channel.send(embed=updated_embed, view=self)
                except:
                    pass

            # Send confirmation to user
            try:
                await interaction.followup.send("Your confirmation has been recorded!", ephemeral=True)
            except:
                pass
    
    async def scam_callback(self, interaction: discord.Interaction):
        """Handle scam report button"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get the other user (if buyer clicked, get seller; if seller clicked, get buyer)
            user_id = interaction.user.id
            if user_id == self.buyer_id:
                scammer_id = self.seller_id
                reporter_role = "Buyer"
                scammer_role = "Seller"
            elif user_id == self.seller_id:
                scammer_id = self.buyer_id
                reporter_role = "Seller"
                scammer_role = "Buyer"
            else:
                await interaction.followup.send(
                    "Only the buyer and seller can report scams.",
                    ephemeral=True
                )
                return
            
            # Create scam report channel
            guild = interaction.guild
            member_role = guild.get_role(1392239599496990791)  # Member role
            
            # Set up permissions for the scam report channel
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True, attach_files=True, embed_links=True)
            }
            
            # Add member role permissions if it exists
            if member_role:
                overwrites[member_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)
            
            # Add moderators/admins to the channel
            for member in guild.members:
                if member.guild_permissions.manage_channels or member.guild_permissions.administrator:
                    overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)
            
            # Create the scam report channel
            scam_channel = await guild.create_text_channel(
                name=f'scam-report-{interaction.user.name}-{self.car_name.lower().replace(" ", "-")}',
                overwrites=overwrites,
                topic=f'Scam report filed by {interaction.user.display_name} regarding {self.car_name}'
            )
            
            # Track channel activity
            from commands.utils import private_channels_activity
            private_channels_activity[scam_channel.id] = asyncio.get_event_loop().time()
            
            # Log to database
            from database_mysql import add_report_ticket
            add_report_ticket(interaction.user.id, f"User ID: {scammer_id}", f"Scam report for deal: {self.car_name}", scam_channel.id)
            
            await interaction.followup.send(
                f"Scam report channel created: {scam_channel.mention}",
                ephemeral=True
            )
            
            # Get scammer information
            try:
                scammer = await interaction.client.fetch_user(scammer_id)
                scammer_member = guild.get_member(scammer_id)
                
                # Get scammer's deal count
                from database_mysql import get_user_sales
                scammer_sales = get_user_sales(scammer_id)
                
                # Create main scam report embed
                embed = discord.Embed(
                    title="🚨 SCAM REPORT",
                    description=f"**Reporter:** {interaction.user.mention} ({reporter_role})\n"
                               f"**Accused Scammer:** {scammer.mention} ({scammer_role})\n"
                               f"**Deal Item:** {self.car_name}",
                    color=discord.Color.red()
                )
                
                # Add scammer information
                embed.add_field(
                    name="🔍 Accused User Information",
                    value=f"**Username:** {scammer.name}\n"
                          f"**Display Name:** {scammer.display_name}\n"
                          f"**User ID:** {scammer.id}\n"
                          f"**Account Created:** <t:{int(scammer.created_at.timestamp())}:F>\n"
                          f"**Total Completed Deals:** {scammer_sales}",
                    inline=False
                )
                
                # Add server join date if available
                if scammer_member:
                    embed.add_field(
                        name="📅 Server Information",
                        value=f"**Joined Server:** <t:{int(scammer_member.joined_at.timestamp())}:F>\n"
                              f"**Roles:** {', '.join([role.mention for role in scammer_member.roles[1:]]) if len(scammer_member.roles) > 1 else 'None'}",
                        inline=False
                    )
                
                # Set scammer's avatar as thumbnail
                if scammer.avatar:
                    embed.set_thumbnail(url=scammer.avatar.url)
                
                embed.timestamp = discord.utils.utcnow()
                
                # Create close button for scam report channel
                from commands.report import ReportChannelView
                view = ReportChannelView(scam_channel.id)
                
                await scam_channel.send(embed=embed, view=view)
                
                # Send all messages from the deal channel
                messages_embed = discord.Embed(
                    title="📝 Deal Channel Messages",
                    description="All messages from the deal channel:",
                    color=discord.Color.orange()
                )
                
                await scam_channel.send(embed=messages_embed)
                
                # Get and send deal channel messages
                deal_messages = []
                async for message in interaction.channel.history(limit=None, oldest_first=True):
                    if not message.author.bot or message.embeds:
                        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                        content = message.content if message.content else "[No text content]"
                        
                        # Handle embeds
                        embed_info = ""
                        if message.embeds:
                            embed_info = f" [Embed: {message.embeds[0].title or 'Untitled'}]"
                        
                        # Handle attachments
                        attachment_info = ""
                        if message.attachments:
                            attachment_info = f" [Attachments: {', '.join([att.filename for att in message.attachments])}]"
                        
                        deal_messages.append(f"**{message.author.display_name}** ({timestamp}): {content}{embed_info}{attachment_info}")
                
                # Send messages in chunks to avoid Discord limits
                if deal_messages:
                    chunk_size = 10
                    for i in range(0, len(deal_messages), chunk_size):
                        chunk = deal_messages[i:i+chunk_size]
                        chunk_text = "\n\n".join(chunk)
                        
                        if len(chunk_text) > 1900:
                            # Split further if still too long
                            for msg in chunk:
                                if len(msg) > 1900:
                                    await scam_channel.send(f"```\n{msg[:1890]}...\n```")
                                else:
                                    await scam_channel.send(f"```\n{msg}\n```")
                        else:
                            await scam_channel.send(f"```\n{chunk_text}\n```")
                        
                        await asyncio.sleep(0.5)  # Rate limit protection
                
                print(f"Created scam report channel: {scam_channel.name}")
                
            except Exception as e:
                print(f"Error creating scam report: {e}")
                await scam_channel.send(f"Error gathering scammer information: {str(e)}")
                
        except Exception as e:
            print(f"Error handling scam report: {e}")
            try:
                await interaction.followup.send(
                    f"Error creating scam report: {str(e)}",
                    ephemeral=True
                )
            except:
                pass

def setup_persistent_deal_confirmation_views(bot):
    """Set up persistent views for deal confirmations on bot restart"""
    # Get all active deal confirmations from database
    from database_mysql import get_all_deal_confirmations, get_all_active_deals

    deal_confirmations = get_all_deal_confirmations()
    active_deals = get_all_active_deals()

    for channel_id, confirmation_data in deal_confirmations.items():
        if channel_id in active_deals:
            deal_info = active_deals[channel_id]

            # Determine if it's a giveaway claim based on channel name
            channel = bot.get_channel(channel_id)
            if channel:
                is_giveaway_claim = (channel.name.startswith('giveaway-claim-') or 
                                   channel.name.startswith('admin-giveaway-claim-'))

                view = DealConfirmationView(
                    channel_id=channel_id,
                    seller_id=deal_info["seller_id"],
                    buyer_id=deal_info["buyer_id"],
                    car_name=deal_info["car_name"],
                    is_giveaway_claim=is_giveaway_claim
                )

                bot.add_view(view)
                print(f"Restored deal confirmation view for channel {channel_id}")

    print(f"Restored {len(deal_confirmations)} deal confirmation views")
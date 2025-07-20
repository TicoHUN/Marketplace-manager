import discord
from discord.ui import Modal, TextInput, View, Button
from discord import app_commands, Interaction, TextStyle, ButtonStyle
import asyncio
import uuid
import random
from datetime import datetime, timedelta
from .utils import (
    listing_timeout, save_image_to_bot_channel, private_channels_activity, 
    send_security_notice
)
from database_mysql import (
    add_pending_listing, get_pending_listing, remove_pending_listing,
    add_active_giveaway, get_active_giveaway, get_all_active_giveaways,
    update_giveaway_participants, remove_active_giveaway, resolve_car_shortcode,
    get_user_sales, add_active_deal
)
from .car_disambiguation import handle_car_disambiguation, CarDisambiguationView
import discord

# Time to wait for an image upload in seconds (90 seconds)
IMAGE_UPLOAD_TIMEOUT = 90

class JoinGiveawayView(discord.ui.View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label='🎉 Join Giveaway', style=discord.ButtonStyle.green)
    async def join_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id

        giveaway = get_active_giveaway(self.giveaway_id)
        if not giveaway:
            await interaction.response.send_message(
                "This giveaway is no longer active.",
                ephemeral=True
            )
            return

        # Check if user already joined
        if user_id in giveaway['participants']:
            await interaction.response.send_message(
                "You already joined this giveaway!",
                ephemeral=True
            )
            return

        # Add user to participants
        participants = giveaway['participants']
        participants.append(user_id)
        update_giveaway_participants(self.giveaway_id, participants)
        participant_count = len(participants)

        # Update the embed with new participant count
        try:
            bot = interaction.client
            embed = discord.Embed(
                title=f"🎁 **{giveaway['car_name'].upper()}**",
                description=f"**Host:** <@{giveaway['host_id']}>\n**Duration:** {giveaway['duration_hours']} hours\n**Ends:** <t:{int(datetime.fromisoformat(giveaway['end_time']).timestamp())}:F>\n\n**Participants:** {participant_count}\n\n🎉 Click the button below to join this giveaway!",
                color=discord.Color.purple()
            )
            embed.set_image(url=interaction.message.embeds[0].image.url)

            try:
                host = await bot.fetch_user(giveaway['host_id'])
                embed.set_footer(text=f"Giveaway by {host.display_name}", icon_url=host.avatar.url if host.avatar else None)
            except:
                embed.set_footer(text="Giveaway")

            # Update the message
            await interaction.response.edit_message(embed=embed)

            print(f"User {interaction.user.display_name} joined giveaway {self.giveaway_id}")

        except Exception as e:
            print(f"Error updating giveaway message: {e}")
            await interaction.response.send_message(
                "You have been added to the giveaway!",
                ephemeral=True
            )

# Channel IDs
GIVEAWAY_CHANNEL_ID = 1394786061540130879 # ID for #make-giveaway channel
GIVEAWAYS_CHANNEL_ID = 1394786059635654817 # ID for #giveaways channel
GIVEAWAY_REVIEW_ID = 1394786040438587503 # ID for #giveaway-review channel

class GiveawayModal(Modal, title='Create Giveaway'):
    car_name = TextInput(
        label='Car Name',
        placeholder='e.g., BMW M5',
        style=TextStyle.short,
        required=True,
        max_length=100
    )
    duration_hours = TextInput(
        label='Giveaway Duration (hours)',
        placeholder='Enter a number between 1 and 48',
        style=TextStyle.short,
        required=True,
        max_length=2
    )

    async def on_submit(self, interaction: Interaction):
        user_id = interaction.user.id

        # Check if user already has a pending listing
        pending_listing = get_pending_listing(user_id, 'giveaway')
        if pending_listing:
            await interaction.response.send_message(
                "You already have a pending giveaway awaiting an image. Please finish or cancel that one first.",
                ephemeral=True
            )
            return

        # Validate duration
        try:
            duration = int(self.duration_hours.value)
            if duration < 1 or duration > 48:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message(
                "Duration must be between 1 and 48 hours!",
                ephemeral=True
            )
            return

        # Resolve car shortcode
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from database_mysql import resolve_car_shortcode
        display_name, original_input, matches = resolve_car_shortcode(self.car_name.value)

        # Handle car disambiguation
        async def proceed_with_giveaway(interaction_or_response, selected_car_name):
            # Store the listing as pending
            listing_data = {
                'car_name': selected_car_name,
                'duration_hours': duration,
                'channel_id': interaction.channel_id,
                'is_admin': interaction.user.guild_permissions.administrator
            }
            add_pending_listing(user_id, 'giveaway', listing_data, interaction.channel_id)

            # Start timeout task with better error handling
            timeout_task = asyncio.create_task(
                listing_timeout(user_id, interaction.channel, 'giveaway')
            )
            timeout_task.add_done_callback(lambda t: print(f"Timeout task completed for user {user_id}"))

            embed = discord.Embed(
                title="🎁 Giveaway Started",
                description=f"**Car:** {selected_car_name}\n"
                           f"**Duration:** {duration} hours\n\n"
                           f"Now upload an image of your car in this channel to complete your giveaway.\n\n"
                           f"⏰ You have 90 seconds to upload the image.",
                color=discord.Color.purple()
            )

            # Use followup for interactions from disambiguation
            await interaction_or_response.followup.send(embed=embed, ephemeral=True)

        # Check if disambiguation is needed
        if len(matches) > 1:
            # Multiple matches - show disambiguation menu
            await handle_car_disambiguation(interaction, self.car_name.value, user_id, proceed_with_giveaway)
        else:
            # Single match or no matches - proceed normally
            embed = discord.Embed(
                title="🎁 Giveaway Started",
                description=f"**Car:** {display_name}\n"
                           f"**Duration:** {duration} hours\n\n"
                           f"Now upload an image of your car in this channel to complete your giveaway.\n\n"
                           f"⏰ You have 90 seconds to upload the image.",
                color=discord.Color.purple()
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

            listing_data = {
                'car_name': display_name,  # Use resolved display name
                'original_input': original_input,  # Store original input
                'duration_hours': duration,
                'channel_id': interaction.channel_id,
                'is_admin': interaction.user.guild_permissions.administrator
            }
            add_pending_listing(user_id, 'giveaway', listing_data, interaction.channel_id)

            # Start timeout task with better error handling
            timeout_task = asyncio.create_task(
                listing_timeout(user_id, interaction.channel, 'giveaway')
            )
            timeout_task.add_done_callback(lambda t: print(f"Timeout task completed for user {user_id}"))

async def handle_giveaway_image_upload(bot, message):
    """Handle image upload for giveaway listings"""
    user_id = message.author.id

    listing_data = get_pending_listing(user_id, 'giveaway')
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
        remove_pending_listing(user_id, 'giveaway')

        car_name = listing_data['car_name']
        duration_hours = listing_data['duration_hours']
        is_admin = listing_data['is_admin']

        # Save the image to the bot channel
        saved_image_url = await save_image_to_bot_channel(
            bot, image_url, "giveaway", car_name, message.author.display_name
        )

        # Delete the user's original image upload message
        try:
            await message.delete()
            print(f"Deleted user's image upload from {message.author} in #{message.channel.name}.")
        except discord.HTTPException as e:
            print(f"Failed to delete the user's image message: {e}")

        if is_admin:
            # Admin - post giveaway directly
            await create_giveaway_directly(bot, message.author, car_name, duration_hours, saved_image_url)
        else:
            # Non-admin - send for review
            await send_giveaway_for_review(bot, message.author, car_name, duration_hours, saved_image_url)
        return True

    else:
        # If user uploaded something but it's not an image while pending
        try:
            await message.delete()
            await message.author.send(
                f"Your previous message in #{message.channel.name} has been deleted. "
                "Please upload a **valid image file** (PNG, JPG, GIF, WEBP) to finalize the car giveaway."
            )
        except discord.HTTPException as e:
            print(f"Failed to handle non-image message: {e}")
        return True

async def create_giveaway_directly(bot, author, car_name, duration_hours, image_url):
    """Create a giveaway directly (for admins)"""
    giveaways_channel = bot.get_channel(GIVEAWAYS_CHANNEL_ID)
    if not giveaways_channel:
        print("ERROR: Could not find giveaways channel!")
        return

    # Create giveaway data
    giveaway_id = str(uuid.uuid4())
    end_time = datetime.utcnow() + timedelta(hours=int(duration_hours))
    host_id = author.id

    # Create embed
    embed = discord.Embed(
        title=f"🎁 **{car_name.upper()}**",
        description=f"**Host:** <@{host_id}>\n**Duration:** {duration_hours} hours\n**Ends:** <t:{int(end_time.timestamp())}:F>\n\n🎉 Click the button below to join this giveaway!",
        color=discord.Color.purple()
    )
    embed.set_image(url=image_url)

    try:
        # Get user's trader role for display
        try:
            from .trader_roles import get_user_trader_role_info
            role_info = await get_user_trader_role_info(bot, author.id)
            if role_info:
                footer_text = f'Giveaway by {author.display_name} • {role_info["role_name"]}'
            else:
                footer_text = f'Giveaway by {author.display_name} • No Trader Role'
        except Exception as e:
            print(f"Error getting trader role for embed: {e}")
            footer_text = f'Giveaway by {author.display_name}'

        embed.set_footer(text=footer_text, icon_url=author.avatar.url if author.avatar else None)
    except:
        embed.set_footer(text="Giveaway")

    # Create a view with the join giveaway button
    view = JoinGiveawayView(giveaway_id)

    # Send the giveaway message
    giveaway_message = await giveaways_channel.send(embed=embed, view=view)

    # Store the giveaway data in database
    giveaway_data = {
        'giveaway_id': giveaway_id,
        'message_id': giveaway_message.id,
        'channel_id': giveaways_channel.id,
        'car_name': car_name,
        'host_id': host_id,
        'end_time': end_time.isoformat(),
        'duration_hours': duration_hours,
        'participants': []
    }
    add_active_giveaway(giveaway_data)

    # Schedule giveaway end
    delay_seconds = int(duration_hours) * 3600
    asyncio.create_task(end_giveaway_timer(bot, giveaway_id, delay_seconds))

    print(f"Created giveaway directly: {car_name}")

async def send_giveaway_for_review(bot, author, car_name, duration_hours, image_url):
    """Send giveaway for moderator review (for non-admins)"""
    review_channel = bot.get_channel(GIVEAWAY_REVIEW_ID)
    if not review_channel:
        print("ERROR: Could not find giveaway review channel!")
        return

    # Get user's sales count
    sales_count = get_user_sales(author.id)

    # Create review embed
    embed = discord.Embed(
        title="🎁 Giveaway Pending Review",
        description=f"**Car:** {car_name}\n**Duration:** {duration_hours} hours\n**Submitted by:** {author.mention} ({author.display_name})\n**User Sales:** {sales_count} completed sales",
        color=discord.Color.yellow()
    )
    embed.set_image(url=image_url)
    embed.set_footer(text=f"User ID: {author.id}")

    # Create approval/rejection buttons
    view = discord.ui.View(timeout=None)

    approve_button = discord.ui.Button(
        label='✅ Approve Giveaway',
        style=ButtonStyle.green,
        custom_id=f'approve_giveaway_{author.id}_{car_name}_{duration_hours}'
    )

    reject_button = discord.ui.Button(
        label='❌ Reject Giveaway',
        style=ButtonStyle.red,
        custom_id=f'reject_giveaway_{author.id}_{car_name}'
    )

    async def approve_callback(button_interaction):
        parts = button_interaction.data['custom_id'].split('_', 3)
        user_id = int(parts[2])
        car_name_from_id = parts[3].split('_')[0]
        duration_from_id = int(parts[3].split('_')[1])

        try:
            user = await bot.fetch_user(user_id)
            await create_giveaway_directly(bot, user, car_name_from_id, duration_from_id, image_url)

            # Update the review message
            approved_embed = discord.Embed(
                title="✅ Giveaway Approved",
                description=f"**Car:** {car_name_from_id}\n**Duration:** {duration_from_id} hours\n**Submitted by:** <@{user_id}>\n**Approved by:** {button_interaction.user.mention}",
                color=discord.Color.green()
            )
            approved_embed.set_image(url=image_url)

            await button_interaction.response.edit_message(embed=approved_embed, view=None)

        except Exception as e:
            await button_interaction.response.send_message(f"Error approving giveaway: {e}", ephemeral=True)

    async def reject_callback(button_interaction):
        parts = button_interaction.data['custom_id'].split('_', 3)
        user_id = int(parts[2])
        car_name_from_id = parts[3]

        try:
            user = await bot.fetch_user(user_id)

            # Send DM to user
            try:
                dm_embed = discord.Embed(
                    title="❌ Giveaway Rejected",
                    description=f"Your giveaway submission for **{car_name_from_id}** has been rejected by the moderation team.",
                    color=discord.Color.red()
                )
                await user.send(embed=dm_embed)
            except discord.Forbidden:
                print(f"Could not send DM to user {user.display_name}")

            # Update the review message
            rejected_embed = discord.Embed(
                title="❌ Giveaway Rejected",
                description=f"**Car:** {car_name_from_id}\n**Submitted by:** <@{user_id}>\n**Rejected by:** {button_interaction.user.mention}",
                color=discord.Color.red()
            )
            rejected_embed.set_image(url=image_url)

            await button_interaction.response.edit_message(embed=rejected_embed, view=None)

        except Exception as e:
            await button_interaction.response.send_message(f"Error rejecting giveaway: {e}", ephemeral=True)

    approve_button.callback = approve_callback
    reject_button.callback = reject_callback
    view.add_item(approve_button)
    view.add_item(reject_button)

    # Send the review message
    await review_channel.send(embed=embed, view=view)
    print(f"Sent giveaway for review: {car_name} by {author.display_name}")

async def handle_giveaway_join(bot, interaction):
    """Handle giveaway join button interactions"""
    giveaway_id = interaction.data['custom_id'].split('_')[2]
    user_id = interaction.user.id

    giveaway = get_active_giveaway(giveaway_id)
    if not giveaway:
        await interaction.response.send_message(
            "This giveaway is no longer active.",
            ephemeral=True
        )
        return

    # Check if user already joined
    if user_id in giveaway['participants']:
        await interaction.response.send_message(
            "You already joined this giveaway!",
            ephemeral=True
        )
        return

    # Add user to participants
    participants = giveaway['participants']
    participants.append(user_id)
    update_giveaway_participants(giveaway_id, participants)
    participant_count = len(participants)

    # Update the embed with new participant count
    try:
        embed = discord.Embed(
            title=f"🎁 **{giveaway['car_name'].upper()}**",
            description=f"**Host:** <@{giveaway['host_id']}>\n**Duration:** {giveaway['duration_hours']} hours\n**Ends:** <t:{int(datetime.fromisoformat(giveaway['end_time']).timestamp())}:F>\n\n**Participants:** {participant_count}\n\n🎉 Click the button below to join this giveaway!",
            color=discord.Color.purple()
        )
        embed.set_image(url=interaction.message.embeds[0].image.url)

        try:
            host = await bot.fetch_user(giveaway['host_id'])
            embed.set_footer(text=f"Giveaway by {host.display_name}", icon_url=host.avatar.url if host.avatar else None)
        except:
            embed.set_footer(text="Giveaway")

        # Update the message
        await interaction.response.edit_message(embed=embed)

        print(f"User {interaction.user.display_name} joined giveaway {giveaway_id}")

    except Exception as e:
        print(f"Error updating giveaway message: {e}")
        await interaction.response.send_message(
            "You have been added to the giveaway!",
            ephemeral=True
        )

async def end_giveaway_timer(bot, giveaway_id, delay_seconds):
    """Timer to end a giveaway"""
    await asyncio.sleep(delay_seconds)
    await end_giveaway(bot, giveaway_id)

async def end_giveaway(bot, giveaway_id):
    """End a giveaway and pick a winner"""
    giveaway = get_active_giveaway(giveaway_id)
    if not giveaway:
        print(f"Warning: Giveaway {giveaway_id} not found in active giveaways")
        return

    try:
        # Get the giveaway channel
        channel = bot.get_channel(giveaway['channel_id'])
        if not channel:
            print(f"Warning: Could not find giveaway channel {giveaway['channel_id']}")
            return

        # Pick a winner
        if giveaway['participants']:
            winner_id = random.choice(giveaway['participants'])
            winner = await bot.fetch_user(winner_id)
            host = await bot.fetch_user(giveaway['host_id'])

            embed = discord.Embed(
                title="🎉 GIVEAWAY ENDED!",
                description=f"**Winner:** {winner.mention}\n**Car:** {giveaway['car_name']}",
                color=discord.Color.gold()
            )

            await channel.send(embed=embed)

            # Create private claim room and handle winner notifications
            await create_giveaway_claim_room(bot, giveaway, winner, host)

        else:
            embed = discord.Embed(
                title="❌ GIVEAWAY ENDED",
                description=f"No one joined the giveaway for **{giveaway['car_name']}**",
                color=discord.Color.red()
            )
            await channel.send(embed=embed)

    except Exception as e:
        print(f"Error ending giveaway {giveaway_id}: {e}")
    finally:
        # Always remove from active giveaways
        remove_active_giveaway(giveaway_id)

async def create_giveaway_claim_room(bot, giveaway, winner, host):
    """Create private claim room for giveaway winner"""
    try:
        # Find a mutual guild
        guild = None
        for g in bot.guilds:
            if g.get_member(winner.id) and g.get_member(host.id):
                guild = g
                break

        if not guild:
            print(f"Error: Could not find mutual guild for giveaway claim room")
            return

        # Check if host is admin
        host_member = guild.get_member(host.id)
        is_admin = host_member.guild_permissions.administrator if host_member else False

        # Create channel name based on host status
        channel_name = f"admin-giveaway-claim-{winner.name}-{host.name}" if is_admin else f"giveaway-claim-{winner.name}-{host.name}"

        if is_admin:
            # Create admin giveaway claim channel
            member_role = guild.get_role(1392239599496990791)  # Member role from rules
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                winner: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True, attach_files=True, embed_links=True)
            }

            # Add member role permissions if it exists
            if member_role:
                overwrites[member_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)

            # Add admins to the channel
            for member in guild.members:
                if member.guild_permissions.administrator:
                    overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)
        else:
            # Create private channel for the claim
            member_role = guild.get_role(1392239599496990791)  # Member role from rules
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                host: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
                winner: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True, attach_files=True, embed_links=True)
            }

            # Add member role permissions if it exists
            if member_role:
                overwrites[member_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)

        # Create the claim channel
        claim_channel = await guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            topic=f'Giveaway claim room for {winner.display_name} - Prize: {giveaway["car_name"]}'
        )

        # Track channel activity
        private_channels_activity[claim_channel.id] = asyncio.get_event_loop().time()

        # Track this as a deal for the close command functionality
        add_active_deal(
            claim_channel.id,
            host.id,  # host as seller
            winner.id,  # winner as buyer
            giveaway['car_name'],
            None  # no listing message for giveaways
        )

        # Send initial message in claim room
        claim_embed = discord.Embed(
            title="🎁 Giveaway Prize Claim",
            description=f"**Prize:** {giveaway['car_name']}\n"
                       f"**Host:** {host.mention} ({host.display_name})\n"
                       f"**Winner:** {winner.mention} ({winner.display_name})\n\n"
                       f"🎉 Congratulations! Please coordinate the prize delivery here.\n\n"
                       f"⚠️ **Important:** Only exchange in-game usernames. Never share personal information or pay real money.",
            color=discord.Color.purple()
        )
        
        # Create view with deal buttons
        from .sell import DealChannelView
        view = DealChannelView(claim_channel.id, host.id, winner.id, giveaway['car_name'])
        await claim_channel.send(embed=claim_embed, view=view)

        # Send security notice
        await send_security_notice(claim_channel)

        # Send DM to winner
        try:
            winner_dm_embed = discord.Embed(
                title="🎉 You Won a Giveaway!",
                description=f"**Prize:** {giveaway['car_name']}\n"
                           f"**Host:** {host.display_name}\n\n"
                           f"A private claim room has been created for you to coordinate with the host.\n\n"
                           f"**Claim Room:** {claim_channel.mention}",
                color=discord.Color.gold()
            )
            await winner.send(embed=winner_dm_embed)
        except discord.Forbidden:
            print(f"Could not send DM to winner {winner.display_name}")

        # Send DM to host
        try:
            host_dm_embed = discord.Embed(
                title="🎁 Your Giveaway Has a Winner!",
                description=f"**Prize:** {giveaway['car_name']}\n"
                           f"**Winner:** {winner.display_name}\n\n"
                           f"A private claim room has been created for you to coordinate with the winner.\n\n"
                           f"**Claim Room:** {claim_channel.mention}",
                color=discord.Color.purple()
            )
            await host.send(embed=host_dm_embed)
        except discord.Forbidden:
            print(f"Could not send DM to host {host.display_name}")

        print(f"Created giveaway claim room: {claim_channel.name}")

    except Exception as e:
        print(f"Error creating giveaway claim room: {e}")

async def restore_active_giveaways(bot):
    """Restore active giveaways after bot restart"""
    all_giveaways = get_all_active_giveaways()
    if not all_giveaways:
        return

    current_time = datetime.utcnow()
    expired_giveaways = []
    restored_count = 0

    for giveaway_id, giveaway_data in all_giveaways.items():
        try:
            # Parse end time
            end_time = datetime.fromisoformat(giveaway_data['end_time'])

            if current_time >= end_time:
                # Giveaway has expired, end it now
                expired_giveaways.append(giveaway_id)
                asyncio.create_task(end_giveaway(bot, giveaway_id))
            else:
                # Restore the interactive button for active giveaways
                try:
                    channel = bot.get_channel(giveaway_data['channel_id'])
                    if channel:
                        message = await channel.fetch_message(giveaway_data['message_id'])

                        # Create a new view with the join button using the same custom_id
                        view = JoinGiveawayView(giveaway_id)

                        # Edit the message to reattach the view
                        await message.edit(view=view)
                        print(f"Restored button for giveaway: {giveaway_data['car_name']}")

                except Exception as button_error:
                    print(f"Error restoring button for giveaway {giveaway_id}: {button_error}")

                # Schedule the remaining time
                remaining_seconds = (end_time - current_time).total_seconds()
                if remaining_seconds > 0:
                    asyncio.create_task(end_giveaway_timer(bot, giveaway_id, remaining_seconds))
                    restored_count += 1

        except Exception as e:
            print(f"Error restoring giveaway {giveaway_id}: {e}")
            expired_giveaways.append(giveaway_id)

    print(f"Restored {restored_count} active giveaways, cleaned up {len(expired_giveaways)} expired ones")

def setup_giveaway_command(tree):
    """Setup the giveaway command"""
    @tree.command(name="giveaway", description="Create a car giveaway")
    @app_commands.default_permissions(administrator=True)
    async def giveaway_command(interaction: Interaction):
        if interaction.channel_id != GIVEAWAY_CHANNEL_ID:
            await interaction.response.send_message(
                "This command can only be used in the #make-giveaway channel.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.send_modal(GiveawayModal())
            print(f"Giveaway modal sent to {interaction.user.display_name}")
        except Exception as e:
            print(f"Error sending giveaway modal: {e}")
            await interaction.response.send_message(
                f"Error starting giveaway: {str(e)}",
                ephemeral=True
            )

    @tree.command(name="clear-pending-giveaway", description="Clear your pending giveaway (admin only)")
    @app_commands.default_permissions(administrator=True)
    async def clear_pending_giveaway(interaction: Interaction, user: discord.Member = None):
        target_user = user or interaction.user

        # Check if user has pending giveaway
        pending_listing = get_pending_listing(target_user.id, 'giveaway')
        if pending_listing:
            remove_pending_listing(target_user.id, 'giveaway')
            await interaction.response.send_message(
                f"✅ Cleared pending giveaway for {target_user.mention}",
                ephemeral=True
            )
            print(f"Manually cleared pending giveaway for user {target_user.id}")
        else:
            await interaction.response.send_message(
                f"No pending giveaway found for {target_user.mention}",
                ephemeral=True
            )

    @tree.command(name="check-all-pending", description="Check all pending listings (admin only)")
    @app_commands.default_permissions(administrator=True)
    async def check_all_pending(interaction: Interaction):
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from database_mysql import get_all_pending_listings

        all_pending = get_all_pending_listings()

        if not all_pending:
            await interaction.response.send_message("No pending listings found.", ephemeral=True)
            return

        message = "**All Pending Listings:**\n"
        for user_id, listings in all_pending.items():
            try:
                user = await interaction.client.fetch_user(user_id)
                username = user.display_name
            except:
                username = f"Unknown User ({user_id})"

            message += f"\n**{username}:**\n"
            for listing_type, data in listings.items():
                message += f"  - {listing_type}: {data.get('car_name', 'Unknown car')}\n"

        if len(message) >2000:
            message = message[:1997] + "..."

        await interaction.response.send_message(message, ephemeral=True)

    @tree.command(name="clear-my-pending", description="Clear your own pending giveaway")
    @app_commands.describe(listing_type="Type of pending listing to clear (giveaway, sell, trade, auction)")
    async def clear_my_pending(interaction: Interaction, listing_type: str = "giveaway"):
        user_id = interaction.user.id

        # Validate listing type
        valid_types = ['giveaway', 'sell', 'trade', 'auction']
        if listing_type not in valid_types:
            await interaction.response.send_message(
                f"Invalid listing type. Must be one of: {', '.join(valid_types)}",
                ephemeral=True
            )
            return

        # Check if user has pending listing of this type
        pending_listing = get_pending_listing(user_id,'giveaway')
        if pending_listing:
            remove_pending_listing(user_id, listing_type)
            await interaction.response.send_message(
                f"✅ Your pending {listing_type} listing has been cleared. You can now create a new {listing_type} listing.",
                ephemeral=True
            )
            print(f"User {interaction.user.display_name} manually cleared their pending {listing_type}")
        else:
            await interaction.response.send_message(
                f"You don't have any pending {listing_type} listing to clear.",
                ephemeral=True
            )

    @tree.command(name="force-clear-all-pending", description="Force clear ALL pending listings (admin only)")
    @app_commands.default_permissions(administrator=True)
    async def force_clear_all_pending(interaction: Interaction):
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from database_mysql import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM pending_listings')
        count = cursor.rowcount
        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"✅ Force cleared {count} pending listings from database",
            ephemeral=True
        )
        print(f"Force cleared {count} pending listings from database")
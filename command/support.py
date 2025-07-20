import discord
from discord.ui import Modal, TextInput, View, Button
from discord import app_commands, Interaction, TextStyle, ButtonStyle
import asyncio

# Import database functions
from database_mysql import add_support_ticket
from .utils import private_channels_activity, log_channel_messages


# Channel IDs
SUPPORT_CHANNEL_ID = 1394786056699641977  # ID for #support channel

class SupportChannelView(discord.ui.View):
    """View for support channel close button"""

    def __init__(self, channel_id: int):
        super().__init__(timeout=None)  # Persistent view
        self.channel_id = channel_id

    @discord.ui.button(label='🔒 Close Support Ticket', style=discord.ButtonStyle.red, custom_id='close_support_ticket')
    async def close_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle close button click"""
        try:
            await interaction.response.defer(ephemeral=True)

            # Send closing message
            closing_embed = discord.Embed(
                title="🔒 Support Ticket Closed",
                description="This support ticket has been closed.\n\n⏳ Channel will be deleted in 10 seconds.",
                color=discord.Color.red()
            )

            await interaction.followup.send(embed=closing_embed, ephemeral=False)

            # Clean up and schedule deletion
            if self.channel_id in private_channels_activity:
                del private_channels_activity[self.channel_id]

            # Schedule channel deletion
            async def delayed_deletion():
                await asyncio.sleep(10)
                try:
                    await log_channel_messages(interaction.client, interaction.channel)
                    await interaction.channel.delete(reason="Support ticket closed")
                    print(f"Deleted support channel: {interaction.channel.name}")
                except Exception as e:
                    print(f"Error deleting support channel: {e}")

            asyncio.create_task(delayed_deletion())

        except Exception as e:
            print(f"Error handling support close: {e}")
            try:
                await interaction.followup.send("Error closing support ticket.", ephemeral=True)
            except:
                pass

class SupportModal(Modal, title='Request Support'):
    help_needed = TextInput(
        label='What help do you need?',
        placeholder='Please describe what kind of help you need',
        style=TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    async def on_submit(self, interaction: Interaction):
        # Create a private support channel
        guild = interaction.guild
        member_role = guild.get_role(1394786020842799235)  # Member role from rules
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

        try:
            channel = await guild.create_text_channel(
                name=f'support-{interaction.user.name}',
                overwrites=overwrites,
                topic=f'Support request by {interaction.user.display_name}'
            )

            # Track channel activity
            private_channels_activity[channel.id] = asyncio.get_event_loop().time()

            # Log to database
            add_support_ticket(interaction.user.id, channel.id, self.help_needed.value)

            await interaction.response.send_message(
                f"Support channel created: {channel.mention}",
                ephemeral=True
            )

            # Send support request details in the private channel
            embed = discord.Embed(
                title="🛠️ Support Request",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Requested By",
                value=interaction.user.mention,
                inline=True
            )
            embed.add_field(
                name="Help Needed",
                value=self.help_needed.value,
                inline=False
            )
            embed.timestamp = discord.utils.utcnow()

            # Create view with close button for support channels
            view = SupportChannelView(channel.id)
            await channel.send(embed=embed, view=view)
            print(f"Created support channel with close button: {channel.name}")

        except Exception as e:
            print(f"Error creating support channel: {e}")
            await interaction.response.send_message(
                f"Error creating support channel: {str(e)}",
                ephemeral=True
            )

def setup_persistent_support_views(bot):
    """Setup persistent views for support channels on bot restart"""
    # Add the persistent view class to the bot so it can handle custom_ids
    bot.add_view(SupportChannelView(0))
    print("Support persistent views setup complete")

async def ensure_support_channel_buttons(bot):
    """Ensure all existing support channels have close buttons"""
    try:
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.name.startswith('support-'):
                    # Check if the channel has recent messages without buttons
                    messages = [message async for message in channel.history(limit=10)]
                    has_button = any(message.components for message in messages if message.author == bot.user)
                    
                    if not has_button:
                        # Add close button to existing support channel with main embed style
                        embed = discord.Embed(
                            title="🛠️ Support Request",
                            description="This support ticket is now equipped with a close button.",
                            color=discord.Color.blue()
                        )
                        embed.add_field(
                            name="Channel Owner",
                            value=f"<@{channel.name.replace('support-', '')}>",
                            inline=True
                        )
                        embed.timestamp = discord.utils.utcnow()
                        view = SupportChannelView(channel.id)
                        await channel.send(embed=embed, view=view)
                        print(f"Added close button to existing support channel: {channel.name}")
    except Exception as e:
        print(f"Error ensuring support channel buttons: {e}")

def setup_support_command(tree):
    """Setup the support command"""
    @tree.command(name="support", description="Request support from moderators.")
    async def support_command(interaction: Interaction):
        if interaction.channel_id != SUPPORT_CHANNEL_ID:
            await interaction.response.send_message(
                "This command can only be used in the #support channel.",
                ephemeral=True
            )
            return
        await interaction.response.send_modal(SupportModal())
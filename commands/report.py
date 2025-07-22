import discord
from discord.ui import Modal, TextInput, View, Button
from discord import app_commands, Interaction, TextStyle, ButtonStyle
import asyncio

# Import database functions
from database_mysql import add_report_ticket
from .utils import private_channels_activity, log_channel_messages

# Channel IDs
SUPPORT_CHANNEL_ID = 1394786056699641977  # ID for #support channel

class ReportChannelView(discord.ui.View):
    """View for report channel close button"""
    
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)  # Persistent view
        self.channel_id = channel_id
        
    @discord.ui.button(label='🔒 Close Report Ticket', style=discord.ButtonStyle.red, custom_id='close_report_ticket')
    async def close_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle close button click"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Send closing message
            closing_embed = discord.Embed(
                title="🔒 Report Ticket Closed",
                description="This report ticket has been closed.\n\n⏳ Channel will be deleted in 10 seconds.",
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
                    await interaction.channel.delete(reason="Report ticket closed")
                    print(f"Deleted report channel: {interaction.channel.name}")
                except Exception as e:
                    print(f"Error deleting report channel: {e}")
            
            asyncio.create_task(delayed_deletion())
            
        except Exception as e:
            print(f"Error handling report close: {e}")
            try:
                await interaction.followup.send("Error closing report ticket.", ephemeral=True)
            except:
                pass

class ReportModal(Modal, title='Report User'):
    username = TextInput(
        label='Username to Report',
        placeholder='Enter the username of the person you want to report',
        style=TextStyle.short,
        required=True,
        max_length=100
    )
    reason = TextInput(
        label='Reason for Report',
        placeholder='Please provide details about why you are reporting this user',
        style=TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    async def on_submit(self, interaction: Interaction):
        # Create a private report channel
        guild = interaction.guild
        member_role = guild.get_role(1392239599496990791)  # Member role from rules
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
                name=f'report-{interaction.user.name}-{self.username.value.lower()}',
                overwrites=overwrites,
                topic=f'Report filed by {interaction.user.display_name} against {self.username.value}'
            )

            # Track channel activity
            private_channels_activity[channel.id] = asyncio.get_event_loop().time()

            # Log to database
            add_report_ticket(interaction.user.id, self.username.value, self.reason.value, channel.id)

            await interaction.response.send_message(
                f"Report channel created: {channel.mention}",
                ephemeral=True
            )

            # Send report details in the private channel
            embed = discord.Embed(
                title="🚨 User Report",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Reported User",
                value=self.username.value,
                inline=True
            )
            embed.add_field(
                name="Reported By",
                value=interaction.user.mention,
                inline=True
            )
            embed.add_field(
                name="Reason",
                value=self.reason.value,
                inline=False
            )
            embed.timestamp = discord.utils.utcnow()

            # Create view with close button for report channels
            view = ReportChannelView(channel.id)
            await channel.send(embed=embed, view=view)
            print(f"Created report channel with close button: {channel.name}")

        except Exception as e:
            print(f"Error creating report channel: {e}")
            await interaction.response.send_message(
                f"Error creating report channel: {str(e)}",
                ephemeral=True
            )

def setup_persistent_report_views(bot):
    """Setup persistent views for report channels on bot restart"""
    # Add the persistent view class to the bot so it can handle custom_ids
    bot.add_view(ReportChannelView(0))
    print("Report persistent views setup complete")

async def ensure_report_channel_buttons(bot):
    """Ensure all existing report channels have close buttons"""
    try:
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.name.startswith('report-'):
                    # Check if the channel has recent messages without buttons
                    messages = [message async for message in channel.history(limit=10)]
                    has_button = any(message.components for message in messages if message.author == bot.user)
                    
                    if not has_button:
                        # Add close button to existing report channel with main embed style
                        embed = discord.Embed(
                            title="🚨 User Report",
                            description="This report ticket is now equipped with a close button.",
                            color=discord.Color.red()
                        )
                        embed.add_field(
                            name="Channel Owner",
                            value=f"<@{channel.name.split('-')[1]}>",
                            inline=True
                        )
                        embed.timestamp = discord.utils.utcnow()
                        view = ReportChannelView(channel.id)
                        await channel.send(embed=embed, view=view)
                        print(f"Added close button to existing report channel: {channel.name}")
    except Exception as e:
        print(f"Error ensuring report channel buttons: {e}")

def setup_report_command(tree):
    """Setup the report command"""
    @tree.command(name="report", description="Report a user to the moderators.")
    @app_commands.default_permissions(administrator=True)
    async def report_command(interaction: Interaction):
        if interaction.channel_id != SUPPORT_CHANNEL_ID:
            await interaction.response.send_message(
                "This command can only be used in the #support channel.",
                ephemeral=True
            )
            return
        await interaction.response.send_modal(ReportModal())
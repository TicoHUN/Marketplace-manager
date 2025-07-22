
import discord
from discord.ui import Modal, TextInput, View, Button
from discord import app_commands, Interaction, TextStyle, ButtonStyle
import asyncio
from .utils import private_channels_activity
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_mysql import add_support_ticket, add_report_ticket

# Channel ID for the support channel
SUPPORT_CHANNEL_ID = 1394786056699641977

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
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
        }

        # Add moderators/admins to the channel
        for member in guild.members:
            if member.guild_permissions.manage_channels or member.guild_permissions.administrator:
                overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

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

            # Import and create close button view
            from .support import SupportChannelView
            view = SupportChannelView(channel.id)
            await channel.send(embed=embed, view=view)
            print(f"Created support channel with close button: {channel.name}")

        except Exception as e:
            print(f"Error creating support channel: {e}")
            await interaction.response.send_message(
                f"Error creating support channel: {str(e)}",
                ephemeral=True
            )

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
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
        }

        # Add moderators/admins to the channel
        for member in guild.members:
            if member.guild_permissions.manage_channels or member.guild_permissions.administrator:
                overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

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

            # Import and create close button view
            from .report import ReportChannelView
            view = ReportChannelView(channel.id)
            await channel.send(embed=embed, view=view)
            print(f"Created report channel with close button: {channel.name}")

        except Exception as e:
            print(f"Error creating report channel: {e}")
            await interaction.response.send_message(
                f"Error creating report channel: {str(e)}",
                ephemeral=True
            )

class TicketButtonView(View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view

    @discord.ui.button(label='🛠️ Support Ticket', style=ButtonStyle.primary, custom_id='support_ticket_button')
    async def support_ticket_button(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(SupportModal())

    @discord.ui.button(label='📢 Report Ticket', style=ButtonStyle.danger, custom_id='report_ticket_button')
    async def report_ticket_button(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(ReportModal())

async def setup_ticket_embed(bot):
    """Setup the persistent ticket embed in the support channel"""
    try:
        channel = bot.get_channel(SUPPORT_CHANNEL_ID)
        if not channel:
            print(f"Support channel with ID {SUPPORT_CHANNEL_ID} not found")
            return

        # Check if embed already exists by looking for recent messages from the bot
        async for message in channel.history(limit=50):
            if (message.author == bot.user and 
                message.embeds and 
                "Ticket System" in message.embeds[0].title):
                print("Ticket embed already exists, skipping creation")
                return

        # Create the embed
        embed = discord.Embed(
            title="🎫 Ticket System",
            description="Need help or want to report something? Use the buttons below to create a ticket:",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🛠️ Support Ticket",
            value="For help, questions, or general issues.",
            inline=False
        )
        
        embed.add_field(
            name="📢 Report Ticket", 
            value="For reporting players, cheating, abuse, or player behavior.",
            inline=False
        )
        
        embed.set_footer(text="Click the appropriate button below to get started")

        # Create the view with persistent buttons
        view = TicketButtonView()
        
        # Send the embed with buttons
        await channel.send(embed=embed, view=view)
        print("Ticket embed sent successfully")

    except Exception as e:
        print(f"Error setting up ticket embed: {e}")

def setup_persistent_views(bot):
    """Add persistent views to the bot"""
    bot.add_view(TicketButtonView())

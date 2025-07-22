
import discord
from discord.ui import View, Button
from discord import Interaction, ButtonStyle
from .giveaway import GiveawayModal

# Channel ID for the giveaway channel
GIVEAWAY_CHANNEL_ID = 1394786061540130879

class GiveawayButtonView(View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view

    @discord.ui.button(label='🎁 Make Giveaway', style=ButtonStyle.success, custom_id='make_giveaway_button')
    async def make_giveaway_button(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(GiveawayModal())

async def setup_giveaway_embed(bot):
    """Setup the persistent giveaway embed in the giveaway channel"""
    try:
        channel = bot.get_channel(GIVEAWAY_CHANNEL_ID)
        if not channel:
            print(f"Giveaway channel with ID {GIVEAWAY_CHANNEL_ID} not found")
            return

        # Check if embed already exists by looking for recent messages from the bot
        async for message in channel.history(limit=50):
            if (message.author == bot.user and 
                message.embeds and 
                "Giveaway System" in message.embeds[0].title):
                print("Giveaway embed already exists, skipping creation")
                return

        # Create the embed
        embed = discord.Embed(
            title="🎁 Giveaway System",
            description="Want to give away a car to the community? Use the button below to create your giveaway:",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="🎁 Make Giveaway",
            value="Create a car giveaway for the community",
            inline=False
        )

        embed.add_field(
            name="📋 How It Works",
            value="1. Click **Make Giveaway** below\n2. Fill in car details and duration (1-48 hours)\n3. Upload a photo of your car\n4. Non-admins: Wait for moderator approval\n5. Admins: Giveaway goes live immediately\n6. Winner is randomly selected when it ends",
            inline=False
        )

        embed.add_field(
            name="🎉 Giveaway Rules",
            value="• Duration: 1-48 hours maximum\n• Must provide a real car photo\n• Non-admin giveaways require approval\n• Winner gets a private claim room\n• Be generous and have fun!",
            inline=False
        )

        embed.add_field(
            name="⚠️ Important Notes",
            value="• Giveaways are for community goodwill\n• Make sure you actually have the car\n• Moderators review non-admin submissions\n• Abuse of the system will result in restrictions",
            inline=False
        )
        
        embed.set_footer(text="Use the button below to create your giveaway | /giveaway command also available for testing")

        # Create the view with persistent buttons
        view = GiveawayButtonView()
        
        # Send the embed with buttons
        await channel.send(embed=embed, view=view)
        print("Giveaway embed sent successfully")

    except Exception as e:
        print(f"Error setting up giveaway embed: {e}")

def setup_persistent_giveaway_views(bot):
    """Add persistent giveaway views to the bot"""
    bot.add_view(GiveawayButtonView())


import discord
from discord.ui import View, Button
from discord import Interaction, ButtonStyle
from .auction import AuctionModal

# Channel ID for the auction channel
AUCTION_CHANNEL_ID = 1394786069534216353

class AuctionButtonView(View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view

    @discord.ui.button(label='🏁 Make Auction', style=ButtonStyle.primary, custom_id='make_auction_button')
    async def make_auction_button(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(AuctionModal(is_test=False))

async def setup_auction_embed(bot):
    """Setup the persistent auction embed in the auction channel"""
    try:
        channel = bot.get_channel(AUCTION_CHANNEL_ID)
        if not channel:
            print(f"Auction channel with ID {AUCTION_CHANNEL_ID} not found")
            return

        # Check if embed already exists by looking for recent messages from the bot
        async for message in channel.history(limit=50):
            if (message.author == bot.user and 
                message.embeds and 
                "Auction System" in message.embeds[0].title):
                print("Auction embed already exists, skipping creation")
                return

        # Create the embed
        embed = discord.Embed(
            title="🏁 Auction System",
            description="Ready to auction your car? Use the button below to get started:",
            color=discord.Color.orange()
        )
        
        embed.add_field(
            name="🏁 Make Auction",
            value="Create a car auction (1-168 hours duration)",
            inline=False
        )

        embed.add_field(
            name="📋 How It Works",
            value="1. Click **Make Auction** below\n2. Fill in your car details, starting bid, and duration\n3. Upload a photo of your car\n4. Your auction goes live in the auction forum!\n5. Users bid by sending numbers in your auction thread",
            inline=False
        )

        embed.add_field(
            name="💡 Auction Rules",
            value="• Duration: 1-168 hours (1 week maximum)\n• Starting bid must be realistic\n• High-quality photos required\n• Only numbers allowed in auction threads\n• Cannot bid on your own auction",
            inline=False
        )

        embed.add_field(
            name="🎯 Bidding Process",
            value="• Auction threads are created in the auction forum\n• Send numbers to place bids\n• Bot automatically processes valid bids\n• 5-minute warning before auction ends\n• Seller can accept or reject the final bid",
            inline=False
        )
        
        embed.set_footer(text="Use the button below to create your auction | /auction command also available for testing")

        # Create the view with persistent buttons
        view = AuctionButtonView()
        
        # Send the embed with buttons
        await channel.send(embed=embed, view=view)
        print("Auction embed sent successfully")

    except Exception as e:
        print(f"Error setting up auction embed: {e}")

def setup_persistent_auction_views(bot):
    """Add persistent auction views to the bot"""
    bot.add_view(AuctionButtonView())

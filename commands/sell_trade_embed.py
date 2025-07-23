
import discord
from discord.ui import View, Button
from discord import Interaction, ButtonStyle
from config import config
from .sell import SellModal
from .trade import TradeModal

# Channel ID for the sell/trade channel
SELL_TRADE_CHANNEL_ID = config.SELL_TRADE_CHANNEL_ID

class SellTradeButtonView(View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view

    @discord.ui.button(label='🚗 Sell Car', style=ButtonStyle.green, custom_id='make_sell_button')
    async def make_sell_button(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(SellModal())

    @discord.ui.button(label='🔄 Trade Car', style=ButtonStyle.primary, custom_id='make_trade_button')
    async def make_trade_button(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(TradeModal())

    @discord.ui.button(label='🗑️ Delete Listing', style=ButtonStyle.red, custom_id='delete_listing_button')
    async def delete_listing_button(self, interaction: Interaction, button: Button):
        # Import handle functions from main module
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Get the handle_delete_command function from main
        import main
        await main.handle_delete_command(interaction)

    @discord.ui.button(label='♻️ Relist Car', style=ButtonStyle.secondary, custom_id='relist_car_button')
    async def relist_car_button(self, interaction: Interaction, button: Button):
        # Import handle functions from main module
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Get the handle_relist_command function from main
        import main
        await main.handle_relist_command(interaction)

async def setup_sell_trade_embed(bot):
    """Setup the persistent sell/trade embed in the sell/trade channel"""
    try:
        channel = bot.get_channel(SELL_TRADE_CHANNEL_ID)
        if not channel:
            print(f"Sell/Trade channel with ID {SELL_TRADE_CHANNEL_ID} not found")
            return

        # Check if embed already exists by looking for recent messages from the bot
        async for message in channel.history(limit=50):
            if (message.author == bot.user and 
                message.embeds and 
                "Sell & Trade System" in message.embeds[0].title):
                print("Sell/Trade embed already exists, skipping creation")
                return

        # Create the embed
        embed = discord.Embed(
            title="🚗 Sell & Trade System",
            description="Ready to sell or trade your car? Use the buttons below to get started:",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="🚗 Sell Car",
            value="List your car for sale with a fixed price",
            inline=True
        )
        
        embed.add_field(
            name="🔄 Trade Car", 
            value="List your car for trade with other vehicles",
            inline=True
        )

        embed.add_field(
            name="🗑️ Delete Listing",
            value="Remove one of your active listings",
            inline=True
        )

        embed.add_field(
            name="♻️ Relist Car",
            value="Move one of your active listings between sell and trade channels as a brand new listing",
            inline=True
        )

        embed.add_field(
            name="📋 How It Works",
            value="1. Click **Sell Car** or **Trade Car** below\n2. Fill in your car details and price/trade preference\n3. Upload a photo of your car\n4. Your listing goes live!\n5. Buyers/traders will contact you through private channels",
            inline=False
        )

        embed.add_field(
            name="💡 Listing Rules",
            value="• Maximum 3 active listings per user\n• Realistic pricing encouraged\n• High-quality photos required\n• Complete all fields accurately",
            inline=False
        )
        
        embed.set_footer(text="Use the buttons below to manage your listings | /sell, /trade, /delete, and /relist commands also available for testing")

        # Create the view with persistent buttons
        view = SellTradeButtonView()
        
        # Send the embed with buttons
        await channel.send(embed=embed, view=view)
        print("Sell/Trade embed sent successfully")

    except Exception as e:
        print(f"Error setting up sell/trade embed: {e}")

def setup_persistent_sell_trade_views(bot):
    """Add persistent sell/trade views to the bot"""
    bot.add_view(SellTradeButtonView())


import discord
from discord.ui import View, Button
from discord import ButtonStyle, Interaction
import asyncio

# Import the new security system
try:
    from security_system import IngameIDModal
    from config import config
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False
    # Fallback configuration
    class config:
        MEMBER_ROLE_ID = 1394786020842799235

# Configuration
RULES_CHANNEL_ID = 1394800414104490147
RULES_ROLE_ID = getattr(config, 'MEMBER_ROLE_ID', 1394786020842799235)

class RulesReactionView(View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view

    @discord.ui.button(label='✅ I Accept the Rules', style=ButtonStyle.green, custom_id='accept_rules_button', emoji='✅')
    async def accept_rules_button(self, interaction: Interaction, button: Button):
        # Check if user already has the member role
        member_role = interaction.guild.get_role(RULES_ROLE_ID)
        if not member_role:
            await interaction.response.send_message("❌ Member role not found. Please contact an administrator.", ephemeral=True)
            return

        if member_role in interaction.user.roles:
            await interaction.response.send_message("✅ You have already accepted the rules and have access to the server!", ephemeral=True)
            return

        # NEW SECURITY SYSTEM: Show ingame ID modal instead of immediately giving role
        if SECURITY_AVAILABLE:
            try:
                modal = IngameIDModal()
                await interaction.response.send_modal(modal)
            except Exception as e:
                print(f"Error showing ingame ID modal: {e}")
                # Fallback to old behavior
                await self._fallback_role_assignment(interaction, member_role)
        else:
            # Fallback to old behavior if security system not available
            await self._fallback_role_assignment(interaction, member_role)

    async def _fallback_role_assignment(self, interaction: Interaction, role: discord.Role):
        """Fallback method for role assignment without security system"""
        try:
            await interaction.user.add_roles(role, reason="Accepted server rules")
            await interaction.response.send_message(
                f"✅ Welcome! You have successfully accepted the rules and received the **{role.name}** role!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Bot doesn't have permission to assign roles. Please contact an administrator.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

async def setup_rules_embed(bot):
    """Setup the persistent rules embed in the rules channel"""
    try:
        channel = bot.get_channel(RULES_CHANNEL_ID)
        if not channel:
            print(f"Rules channel with ID {RULES_CHANNEL_ID} not found")
            return

        # Check if embed already exists by looking for recent messages from the bot
        async for message in channel.history(limit=50):
            if (message.author == bot.user and 
                message.embeds and 
                "Server Rules & Bot Usage Guide" in message.embeds[0].title):
                print("Rules embed already exists, skipping creation")
                return

        # Create the rules embed
        embed = discord.Embed(
            title="📋 Server Rules & Bot Usage Guide",
            description="Welcome to our server! Please read and accept the rules below to gain access to all channels.",
            color=discord.Color.blue()
        )

        # Bot Usage Rules
        embed.add_field(
            name="🤖 Bot Usage Rules",
            value="• **Use bot commands in designated channels only**\n"
                  "• **Maximum 3 active listings per user**\n"
                  "• **Provide accurate information** in all listings\n"
                  "• **Upload high-quality photos** for your cars\n"
                  "• **No fake or misleading listings**\n"
                  "• **Complete deals through the bot's private channels**\n"
                  "• **Never exchange real money** - in-game items only",
            inline=False
        )

        # Bot Functions Guide
        embed.add_field(
            name="🔧 Where to Find Bot Functions",
            value="**🚗 #make-sell-trade** - Sell & trade cars, manage listings\n"
                  "**🏁 #auction** - Create and participate in car auctions\n"
                  "**🎁 #giveaway** - Host and join community giveaways\n"
                  "**🎫 #support** - Get help or report issues",
            inline=False
        )

        # Trading Safety
        embed.add_field(
            name="🛡️ Trading Safety",
            value="• **All trades must stay in bot-created channels**\n"
                  "• **Never move to DMs** - trades must be public\n"
                  "• **Report suspicious behavior** immediately\n"
                  "• **Use the `/close` command** to confirm deals\n"
                  "• **Bot monitors for risky keywords** automatically",
            inline=False
        )

        embed.add_field(
            name="⚠️ Important Notes",
            value="• **Violation of rules may result in warnings, mutes, or bans**\n"
                  "• **All activities are logged for safety**\n"
                  "• **Contact staff if you need help understanding any rule**\n"
                  "• **Rules may be updated - check back occasionally**",
            inline=False
        )

        embed.set_footer(
            text="Click the button below to accept the rules and gain access to the server • Rules last updated",
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )
        embed.timestamp = discord.utils.utcnow()

        # Create the view with the accept button
        view = RulesReactionView()

        # Send the embed with the button
        await channel.send(embed=embed, view=view)
        print("Rules embed sent successfully with reaction role button")

    except Exception as e:
        print(f"Error setting up rules embed: {e}")

def setup_persistent_rules_views(bot):
    """Setup persistent views for rules reactions"""
    bot.add_view(RulesReactionView())
    print("Persistent rules views setup complete")

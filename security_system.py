"""
Discord Bot Security System - Ingame ID Management
=================================================

This module provides comprehensive security features including:
- Ingame ID validation and registration
- Deal channel monitoring for ID mismatches  
- Anti-fraud protection and scam detection
- Admin tools for ID management

Features:
- Format validation (2 letters + 6 numbers, e.g., RC463713)
- Duplicate detection
- Real-time monitoring in deal channels
- Automatic warnings for potential scams
- Admin override capabilities
"""

import discord
from discord.ui import Modal, TextInput, View, Button
from discord import app_commands, Interaction, TextStyle, ButtonStyle
import asyncio
import re
from typing import Optional, List, Tuple, Dict, Any

# Try to import dependencies with fallbacks
try:
    from config import config
    from logger_config import get_logger, log_info, log_error, log_warning
    from database_mysql import (
        validate_ingame_id_format, add_user_ingame_id, get_user_ingame_id,
        ingame_id_exists, update_user_ingame_id, extract_ingame_ids_from_text,
        get_discord_by_ingame_id
    )
    logger = get_logger("security")
except ImportError:
    # Fallback for testing
    class config:
        MEMBER_ROLE_ID = config.MEMBER_ROLE_ID
    
    def log_info(msg, module=None): print(f"INFO: {msg}")
    def log_error(msg, module=None, exc_info=False): print(f"ERROR: {msg}")
    def log_warning(msg, module=None): print(f"WARNING: {msg}")
    
    # Mock functions for testing
    def validate_ingame_id_format(id): return bool(re.match(r'^[A-Z]{2}\d{6}$', id))
    def add_user_ingame_id(discord_id, ingame_id): return True
    def get_user_ingame_id(discord_id): return None
    def ingame_id_exists(ingame_id): return False
    def update_user_ingame_id(discord_id, ingame_id): return True
    def extract_ingame_ids_from_text(text): return re.findall(r'[A-Z]{2}\d{6}', text.upper())
    def get_discord_by_ingame_id(ingame_id): return None

# Constants
INGAME_ID_PATTERN = re.compile(r'^[A-Z]{2}\d{6}$')
INGAME_ID_EXTRACT_PATTERN = re.compile(r'[A-Z]{2}\d{6}')

class IngameIDModal(Modal, title='Register Your Ingame ID'):
    """Modal for collecting user's ingame ID during rule acceptance"""
    
    ingame_id = TextInput(
        label='Your Ingame ID',
        placeholder='e.g., RC463713 (2 letters + 6 numbers)',
        style=TextStyle.short,
        required=True,
        max_length=8,
        min_length=8
    )

    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: Interaction):
        """Handle ingame ID submission"""
        try:
            submitted_id = self.ingame_id.value.strip().upper()
            
            # Validate format
            if not validate_ingame_id_format(submitted_id):
                await self._send_format_error_dm(interaction, submitted_id)
                await interaction.response.send_message(
                    "❌ Invalid ingame ID format. Please check your DMs for details.",
                    ephemeral=True
                )
                return
            
            # Check if ID already exists
            if ingame_id_exists(submitted_id):
                await self._send_duplicate_error_dm(interaction, submitted_id)
                await interaction.response.send_message(
                    "❌ This ingame ID is already registered. Please check your DMs for details.",
                    ephemeral=True
                )
                return
            
            # Check if user already has an ID registered
            existing_id = get_user_ingame_id(interaction.user.id)
            if existing_id:
                await self._send_already_registered_dm(interaction, existing_id)
                await interaction.response.send_message(
                    "❌ You already have an ingame ID registered. Please check your DMs for details.",
                    ephemeral=True
                )
                return
            
            # Register the ID
            success = add_user_ingame_id(interaction.user.id, submitted_id)
            if not success:
                await interaction.response.send_message(
                    "❌ Failed to register your ingame ID. Please try again or contact support.",
                    ephemeral=True
                )
                return
            
            # Give member role
            member_role = interaction.guild.get_role(config.MEMBER_ROLE_ID)
            if not member_role:
                await interaction.response.send_message(
                    "❌ Member role not found. Please contact an administrator.",
                    ephemeral=True
                )
                return
            
            try:
                await interaction.user.add_roles(member_role, reason="Accepted rules and registered ingame ID")
                
                # Success response
                success_embed = discord.Embed(
                    title="✅ Registration Successful!",
                    description=f"**Welcome to the server!**\n\n"
                               f"• **Ingame ID:** `{submitted_id}`\n"
                               f"• **Role:** {member_role.mention}\n"
                               f"• **Status:** Verified\n\n"
                               f"You now have access to all server channels. "
                               f"Your ingame ID is linked to your Discord account for security purposes.",
                    color=discord.Color.green()
                )
                success_embed.set_footer(text="This ID will be monitored in deal channels to prevent fraud")
                
                await interaction.response.send_message(embed=success_embed, ephemeral=True)
                
                # Log successful registration
                log_info(f"User {interaction.user.id} ({interaction.user.display_name}) registered ingame ID: {submitted_id}")
                
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ Bot doesn't have permission to assign roles. Please contact an administrator.",
                    ephemeral=True
                )
            except Exception as e:
                log_error(f"Error assigning member role: {e}", exc_info=True)
                await interaction.response.send_message(
                    "❌ Error assigning member role. Please contact an administrator.",
                    ephemeral=True
                )
                
        except Exception as e:
            log_error(f"Error in ingame ID submission: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An unexpected error occurred. Please try again or contact support.",
                ephemeral=True
            )

    async def _send_format_error_dm(self, interaction: Interaction, submitted_id: str):
        """Send DM about format error"""
        try:
            embed = discord.Embed(
                title="❌ Invalid Ingame ID Format",
                description=f"**Your submission:** `{submitted_id}`\n\n"
                           f"**Required format:** 2 letters + 6 numbers\n"
                           f"**Examples:** `RC463713`, `AB123456`, `XY789012`\n\n"
                           f"**Your ID must:**\n"
                           f"• Start with exactly 2 capital letters\n"
                           f"• Be followed by exactly 6 numbers\n"
                           f"• Be exactly 8 characters total\n\n"
                           f"Please return to the rules channel and try again with the correct format.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Need help? Contact support in the #support channel")
            await interaction.user.send(embed=embed)
        except:
            pass  # User has DMs disabled

    async def _send_duplicate_error_dm(self, interaction: Interaction, submitted_id: str):
        """Send DM about duplicate ID"""
        try:
            embed = discord.Embed(
                title="❌ Ingame ID Already Registered",
                description=f"**The ingame ID `{submitted_id}` is already linked to another Discord account.**\n\n"
                           f"**This means:**\n"
                           f"• Someone else has already registered this ID\n"
                           f"• You may have typed the wrong ID\n"
                           f"• This could be a security issue\n\n"
                           f"**What to do:**\n"
                           f"• Double-check your ingame ID is correct\n"
                           f"• If this is your ID, contact support immediately\n"
                           f"• If you made a mistake, try again with your correct ID",
                color=discord.Color.red()
            )
            embed.set_footer(text="Contact support in #support if this is your legitimate ID")
            await interaction.user.send(embed=embed)
        except:
            pass

    async def _send_already_registered_dm(self, interaction: Interaction, existing_id: str):
        """Send DM about already having an ID"""
        try:
            embed = discord.Embed(
                title="❌ Already Registered",
                description=f"**You already have an ingame ID registered.**\n\n"
                           f"**Your current ID:** `{existing_id}`\n\n"
                           f"**You cannot:**\n"
                           f"• Register multiple IDs\n"
                           f"• Change your ID yourself\n"
                           f"• Use different IDs for different deals\n\n"
                           f"**If you need to change your ID:**\n"
                           f"• Contact an administrator\n"
                           f"• Provide a valid reason\n"
                           f"• Use the #support channel",
                color=discord.Color.orange()
            )
            embed.set_footer(text="This restriction prevents fraud and multi-accounting")
            await interaction.user.send(embed=embed)
        except:
            pass

class SecurityMonitor:
    """Monitors deal channels for ingame ID mismatches and potential fraud"""
    
    @staticmethod
    async def check_message_for_id_mismatch(message: discord.Message) -> bool:
        """
        Check a message for ingame ID mismatches
        Returns True if a warning was sent, False otherwise
        """
        try:
            # Extract potential ingame IDs from the message
            found_ids = extract_ingame_ids_from_text(message.content)
            if not found_ids:
                return False
            
            # Get the sender's registered ingame ID
            registered_id = get_user_ingame_id(message.author.id)
            if not registered_id:
                # User hasn't registered an ID yet - send warning
                await SecurityMonitor._send_unregistered_warning(message)
                return True
            
            # Check if any found IDs don't match the registered ID
            mismatched_ids = [id for id in found_ids if id != registered_id]
            if mismatched_ids:
                await SecurityMonitor._send_mismatch_warning(message, registered_id, mismatched_ids)
                return True
                
            return False
            
        except Exception as e:
            log_error(f"Error checking message for ID mismatch: {e}", exc_info=True)
            return False
    
    @staticmethod
    async def _send_unregistered_warning(message: discord.Message):
        """Send warning when user shares ID but isn't registered"""
        try:
            embed = discord.Embed(
                title="⚠️ Unregistered User Sharing Ingame ID",
                description=f"**{message.author.mention} appears to be sharing an ingame ID but is not registered in our security system.**\n\n"
                           f"**Security Notice:**\n"
                           f"• This user bypassed the normal registration process\n"
                           f"• Their identity cannot be verified\n"
                           f"• **Proceed with extreme caution**\n\n"
                           f"**Recommendation:** Ask them to complete registration through the rules channel first.",
                color=discord.Color.red()
            )
            embed.set_footer(text="This is an automated security alert")
            await message.channel.send(embed=embed)
            
            # Log the incident
            log_warning(f"Unregistered user {message.author.id} sharing ingame ID in {message.channel.name}")
            
        except Exception as e:
            log_error(f"Error sending unregistered warning: {e}")
    
    @staticmethod
    async def _send_mismatch_warning(message: discord.Message, registered_id: str, mismatched_ids: List[str]):
        """Send warning when registered ID doesn't match shared ID"""
        try:
            embed = discord.Embed(
                title="🚨 SECURITY ALERT: Ingame ID Mismatch Detected",
                description=f"**{message.author.mention} is using a different ingame ID than registered!**\n\n"
                           f"**Registered ID:** `{registered_id}`\n"
                           f"**Used in message:** {', '.join([f'`{id}`' for id in mismatched_ids])}\n\n"
                           f"**⚠️ WARNING SIGNS OF POTENTIAL SCAM:**\n"
                           f"• User is sharing different ingame ID\n"
                           f"• This could be identity theft\n"
                           f"• **DO NOT PROCEED WITH THIS DEAL**\n\n"
                           f"**{message.author.mention}** - If this is a mistake, use your registered ID: `{registered_id}`",
                color=discord.Color.red()
            )
            embed.set_footer(text="🛡️ Automated Security System • Report this to admins if suspicious")
            await message.channel.send(embed=embed)
            
            # Log the incident
            log_warning(f"ID mismatch detected: User {message.author.id} (registered: {registered_id}) used {mismatched_ids} in {message.channel.name}")
            
        except Exception as e:
            log_error(f"Error sending mismatch warning: {e}")

def setup_security_monitoring():
    """Initialize the security monitoring system"""
    log_info("Security monitoring system initialized")
    return SecurityMonitor()

# Export key functions
__all__ = [
    'IngameIDModal',
    'SecurityMonitor', 
    'setup_security_monitoring',
    'validate_ingame_id_format',
    'INGAME_ID_PATTERN'
]
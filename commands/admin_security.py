"""
Admin Security Commands
======================

This module provides admin-only commands for managing the security system:
- /changeid - Change a user's ingame ID
- /viewid - View a user's ingame ID  
- /listids - List all registered IDs (admin only)
- /deleteid - Remove a user's ingame ID

All commands require administrator permissions.
"""

import discord
from discord import app_commands, Interaction
from typing import Optional

# Try to import dependencies with fallbacks
try:
    from config import config
    from logger_config import get_logger, log_info, log_error, log_warning
    from database_mysql import (
        validate_ingame_id_format, get_user_ingame_id, update_user_ingame_id,
        add_user_ingame_id, ingame_id_exists, delete_user_ingame_id,
        get_all_ingame_ids, get_discord_by_ingame_id
    )
    logger = get_logger("admin_security")
except ImportError:
    # Fallback for testing
    def log_info(msg, module=None): print(f"INFO: {msg}")
    def log_error(msg, module=None, exc_info=False): print(f"ERROR: {msg}")
    def log_warning(msg, module=None): print(f"WARNING: {msg}")
    
    # Mock functions for testing
    def validate_ingame_id_format(id): return True
    def get_user_ingame_id(discord_id): return None
    def update_user_ingame_id(discord_id, ingame_id): return True
    def add_user_ingame_id(discord_id, ingame_id): return True
    def ingame_id_exists(ingame_id): return False
    def delete_user_ingame_id(discord_id): return True
    def get_all_ingame_ids(): return []
    def get_discord_by_ingame_id(ingame_id): return None

def setup_admin_security_commands(tree: app_commands.CommandTree):
    """Setup admin security commands"""
    
    @tree.command(name="changeid", description="[ADMIN] Change a user's ingame ID")
    @app_commands.describe(
        user="The user whose ingame ID to change",
        new_id="The new ingame ID (format: 2 letters + 6 numbers, e.g., RC463713)"
    )
    @app_commands.default_permissions(administrator=True)
    async def changeid_command(interaction: Interaction, user: discord.Member, new_id: str):
        """Change a user's ingame ID (admin only)"""
        
        # Check admin permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ This command requires administrator permissions.",
                ephemeral=True
            )
            return
        
        try:
            # Validate new ID format
            new_id = new_id.strip().upper()
            if not validate_ingame_id_format(new_id):
                embed = discord.Embed(
                    title="❌ Invalid Ingame ID Format",
                    description=f"**Invalid ID:** `{new_id}`\n\n"
                               f"**Required format:** 2 letters + 6 numbers\n"
                               f"**Examples:** `RC463713`, `AB123456`, `XY789012`",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Check if new ID already exists (and isn't owned by this user)
            existing_owner = get_discord_by_ingame_id(new_id)
            if existing_owner and existing_owner != user.id:
                existing_user = await interaction.guild.fetch_member(existing_owner)
                embed = discord.Embed(
                    title="❌ Ingame ID Already Registered",
                    description=f"**The ingame ID `{new_id}` is already registered to:**\n"
                               f"{existing_user.mention} ({existing_user.display_name})\n\n"
                               f"Please choose a different ID or remove it from the other user first.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Get current ID
            current_id = get_user_ingame_id(user.id)
            
            # Update or add the ID
            if current_id:
                success = update_user_ingame_id(user.id, new_id)
                action = "updated"
            else:
                success = add_user_ingame_id(user.id, new_id)
                action = "added"
            
            if success:
                embed = discord.Embed(
                    title="✅ Ingame ID Successfully Changed",
                    description=f"**User:** {user.mention} ({user.display_name})\n"
                               f"**Previous ID:** `{current_id or 'None'}`\n"
                               f"**New ID:** `{new_id}`\n"
                               f"**Action:** {action.title()}\n\n"
                               f"The change has been logged and will take effect immediately.",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Changed by {interaction.user.display_name}")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
                # Log the change
                log_info(f"Admin {interaction.user.id} changed ingame ID for user {user.id}: {current_id} -> {new_id}")
                
                # Try to DM the user about the change
                try:
                    user_embed = discord.Embed(
                        title="🔄 Your Ingame ID Has Been Changed",
                        description=f"**An administrator has updated your ingame ID:**\n\n"
                                   f"**Previous ID:** `{current_id or 'None'}`\n"
                                   f"**New ID:** `{new_id}`\n"
                                   f"**Changed by:** {interaction.user.display_name}\n\n"
                                   f"This change takes effect immediately. "
                                   f"Use your new ID in all future deals.",
                        color=discord.Color.blue()
                    )
                    await user.send(embed=user_embed)
                except:
                    pass  # User has DMs disabled
                    
            else:
                await interaction.response.send_message(
                    "❌ Failed to change ingame ID. Please try again or check the logs.",
                    ephemeral=True
                )
                
        except Exception as e:
            log_error(f"Error in changeid command: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while changing the ingame ID.",
                ephemeral=True
            )
    
    @tree.command(name="viewid", description="[ADMIN] View a user's ingame ID")
    @app_commands.describe(user="The user whose ingame ID to view")
    @app_commands.default_permissions(administrator=True)
    async def viewid_command(interaction: Interaction, user: discord.Member):
        """View a user's ingame ID (admin only)"""
        
        # Check admin permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ This command requires administrator permissions.",
                ephemeral=True
            )
            return
        
        try:
            ingame_id = get_user_ingame_id(user.id)
            
            if ingame_id:
                embed = discord.Embed(
                    title="🔍 User Ingame ID",
                    description=f"**User:** {user.mention} ({user.display_name})\n"
                               f"**Ingame ID:** `{ingame_id}`\n"
                               f"**Status:** ✅ Registered",
                    color=discord.Color.blue()
                )
            else:
                embed = discord.Embed(
                    title="🔍 User Ingame ID",
                    description=f"**User:** {user.mention} ({user.display_name})\n"
                               f"**Ingame ID:** `Not registered`\n"
                               f"**Status:** ❌ No ID on file",
                    color=discord.Color.orange()
                )
            
            embed.set_footer(text=f"Requested by {interaction.user.display_name}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            log_error(f"Error in viewid command: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while viewing the ingame ID.",
                ephemeral=True
            )
    
    @tree.command(name="listids", description="[ADMIN] List all registered ingame IDs")
    @app_commands.default_permissions(administrator=True)
    async def listids_command(interaction: Interaction):
        """List all registered ingame IDs (admin only)"""
        
        # Check admin permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ This command requires administrator permissions.",
                ephemeral=True
            )
            return
        
        try:
            all_ids = get_all_ingame_ids()
            
            if not all_ids:
                embed = discord.Embed(
                    title="📋 Registered Ingame IDs",
                    description="No ingame IDs are currently registered.",
                    color=discord.Color.orange()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Create pages if there are many IDs
            embed = discord.Embed(
                title="📋 Registered Ingame IDs",
                description=f"**Total registered:** {len(all_ids)}\n\n",
                color=discord.Color.blue()
            )
            
            # Show first 20 entries
            for i, id_data in enumerate(all_ids[:20]):
                try:
                    user = await interaction.guild.fetch_member(id_data['discord_id'])
                    username = user.display_name
                except:
                    username = f"Unknown User ({id_data['discord_id']})"
                
                embed.add_field(
                    name=f"`{id_data['ingame_id']}`",
                    value=f"{username}\nRegistered: <t:{int(id_data['created_at'].timestamp())}:R>",
                    inline=True
                )
            
            if len(all_ids) > 20:
                embed.set_footer(text=f"Showing first 20 of {len(all_ids)} entries")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            log_error(f"Error in listids command: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while listing ingame IDs.",
                ephemeral=True
            )
    
    @tree.command(name="deleteid", description="[ADMIN] Remove a user's ingame ID")
    @app_commands.describe(user="The user whose ingame ID to remove")
    @app_commands.default_permissions(administrator=True)
    async def deleteid_command(interaction: Interaction, user: discord.Member):
        """Remove a user's ingame ID (admin only)"""
        
        # Check admin permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ This command requires administrator permissions.",
                ephemeral=True
            )
            return
        
        try:
            current_id = get_user_ingame_id(user.id)
            
            if not current_id:
                embed = discord.Embed(
                    title="❌ No Ingame ID Found",
                    description=f"**User:** {user.mention} ({user.display_name})\n\n"
                               f"This user does not have an ingame ID registered.",
                    color=discord.Color.orange()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Delete the ID
            success = delete_user_ingame_id(user.id)
            
            if success:
                embed = discord.Embed(
                    title="✅ Ingame ID Removed",
                    description=f"**User:** {user.mention} ({user.display_name})\n"
                               f"**Removed ID:** `{current_id}`\n\n"
                               f"The user will need to re-register their ingame ID "
                               f"through the rules channel to regain access.",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Removed by {interaction.user.display_name}")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
                # Log the deletion
                log_info(f"Admin {interaction.user.id} deleted ingame ID {current_id} for user {user.id}")
                
                # Try to DM the user about the removal
                try:
                    user_embed = discord.Embed(
                        title="🗑️ Your Ingame ID Has Been Removed",
                        description=f"**An administrator has removed your ingame ID:**\n\n"
                                   f"**Removed ID:** `{current_id}`\n"
                                   f"**Removed by:** {interaction.user.display_name}\n\n"
                                   f"To regain access to the server, you'll need to "
                                   f"re-register your ingame ID through the rules channel.",
                        color=discord.Color.red()
                    )
                    await user.send(embed=user_embed)
                except:
                    pass  # User has DMs disabled
                    
            else:
                await interaction.response.send_message(
                    "❌ Failed to remove ingame ID. Please try again or check the logs.",
                    ephemeral=True
                )
                
        except Exception as e:
            log_error(f"Error in deleteid command: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while removing the ingame ID.",
                ephemeral=True
            )

    log_info("Admin security commands setup complete")

# Export the setup function
__all__ = ['setup_admin_security_commands']
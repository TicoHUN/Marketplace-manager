
import discord

# Import database functions
from database_mysql import get_user_sales
from typing import Dict, List, Optional, Tuple

# Trader role configuration - easily adjustable
TRADER_ROLES = [
    {"name": "New Trader", "threshold": 1, "role_id": 1395188236967481515},
    {"name": "Junior Trader", "threshold": 5, "role_id": 1395188500818558976},
    {"name": "Skilled Trader", "threshold": 10, "role_id": 1395188647283916900},
    {"name": "Verified Trader", "threshold": 20, "role_id": 1395188894160650371},
    {"name": "Trusted Trader", "threshold": 35, "role_id": 1395189106052694116},
    {"name": "Pro Trader", "threshold": 50, "role_id": 1395189318737465466},
    {"name": "Elite Trader", "threshold": 75, "role_id": 1395189499923005450},
    {"name": "Prime Trader", "threshold": 100, "role_id": 1395189718983114782},
    {"name": "Legend Trader", "threshold": 150, "role_id": 1395190134718337044},
]

# Sort roles by threshold (highest first) for efficient checking
TRADER_ROLES_SORTED = sorted(TRADER_ROLES, key=lambda x: x["threshold"], reverse=True)

def get_trader_role_ids() -> List[int]:
    """Get all trader role IDs for easy removal"""
    return [role["role_id"] for role in TRADER_ROLES]



def determine_trader_role(deal_count: int) -> Optional[Dict]:
    """
    Determine the appropriate trader role based on deal count.
    Returns the role info dict or None if no role qualifies.
    """
    for role in TRADER_ROLES_SORTED:
        if deal_count >= role["threshold"]:
            return role
    return None

async def update_trader_role(bot: discord.Client, user_id: int, new_deal_count: int) -> Tuple[bool, str]:
    """
    Update a user's trader role based on their deal count.
    
    Args:
        bot: Discord bot instance
        user_id: Discord user ID
        new_deal_count: User's current confirmed deal count
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Determine the appropriate role
        target_role_info = determine_trader_role(new_deal_count)
        
        # Get all trader role IDs for removal
        all_trader_role_ids = get_trader_role_ids()
        
        # Find the user in all guilds the bot is in
        user = None
        guild = None
        
        for guild_obj in bot.guilds:
            member = guild_obj.get_member(user_id)
            if member:
                user = member
                guild = guild_obj
                break
        
        if not user or not guild:
            return False, f"User {user_id} not found in any guild"
        
        # Check bot permissions
        if not guild.me.guild_permissions.manage_roles:
            return False, "Bot lacks 'Manage Roles' permission"
        
        # Get current trader roles the user has
        current_trader_roles = [role for role in user.roles if role.id in all_trader_role_ids]
        
        # If no role should be assigned
        if not target_role_info:
            if current_trader_roles:
                # Remove all trader roles
                for role in current_trader_roles:
                    try:
                        await user.remove_roles(role, reason=f"Deal count ({new_deal_count}) below minimum threshold")
                    except discord.Forbidden:
                        return False, f"Cannot remove role '{role.name}' - insufficient permissions"
                    except discord.HTTPException as e:
                        return False, f"Failed to remove role '{role.name}': {e}"
                
                return True, f"Removed trader roles (deal count: {new_deal_count})"
            else:
                return True, f"No trader role needed (deal count: {new_deal_count})"
        
        # Get the target role object
        target_role = guild.get_role(target_role_info["role_id"])
        if not target_role:
            return False, f"Target role '{target_role_info['name']}' (ID: {target_role_info['role_id']}) not found in guild"
        
        # Check if bot can manage this role
        if target_role >= guild.me.top_role:
            return False, f"Cannot assign role '{target_role.name}' - role is higher than bot's highest role"
        
        # Check if user already has the correct role
        if target_role in user.roles:
            # Remove any other trader roles they shouldn't have
            roles_to_remove = [role for role in current_trader_roles if role.id != target_role.id]
            if roles_to_remove:
                try:
                    await user.remove_roles(*roles_to_remove, reason=f"Updating to correct trader role: {target_role.name}")
                except discord.Forbidden:
                    return False, f"Cannot remove old trader roles - insufficient permissions"
                except discord.HTTPException as e:
                    return False, f"Failed to remove old trader roles: {e}"
                
                return True, f"Updated to {target_role.name} (deal count: {new_deal_count})"
            else:
                return True, f"User already has correct role: {target_role.name} (deal count: {new_deal_count})"
        
        # Remove all current trader roles first
        if current_trader_roles:
            try:
                await user.remove_roles(*current_trader_roles, reason=f"Updating trader role to: {target_role.name}")
            except discord.Forbidden:
                return False, f"Cannot remove old trader roles - insufficient permissions"
            except discord.HTTPException as e:
                return False, f"Failed to remove old trader roles: {e}"
        
        # Add the new role
        try:
            await user.add_roles(target_role, reason=f"Achieved {new_deal_count} confirmed deals")
            return True, f"Assigned {target_role.name} role (deal count: {new_deal_count})"
        except discord.Forbidden:
            return False, f"Cannot assign role '{target_role.name}' - insufficient permissions"
        except discord.HTTPException as e:
            return False, f"Failed to assign role '{target_role.name}': {e}"
    
    except Exception as e:
        return False, f"Unexpected error updating trader role: {e}"

async def get_user_trader_role_info(bot: discord.Client, user_id: int) -> Optional[Dict]:
    """
    Get information about a user's current trader role.
    
    Returns:
        Dict with role info or None if no trader role
    """
    try:
        from database_postgres import get_user_sales
        
        # Get user's sales count
        sales_count = get_user_sales(user_id)
        
        # Determine what role they should have based on sales
        earned_role = determine_trader_role(sales_count)
        
        if not earned_role:
            return None
        
        # Find the user in guilds to check their actual Discord roles
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member:
                # Get the Discord role object if it exists
                discord_role = guild.get_role(earned_role["role_id"])
                return {
                    "role_name": earned_role["name"],
                    "role_id": earned_role["role_id"],
                    "threshold": earned_role["threshold"],
                    "sales_count": sales_count,
                    "discord_role": discord_role
                }
        
        # Return role info even if user not found in guild (for display purposes)
        return {
            "role_name": earned_role["name"],
            "role_id": earned_role["role_id"],
            "threshold": earned_role["threshold"],
            "sales_count": sales_count,
            "discord_role": None
        }
    
    except Exception as e:
        print(f"Error getting user trader role info: {e}")
        return None

def get_next_role_info(current_deal_count: int) -> Optional[Dict]:
    """
    Get information about the next trader role the user can achieve.
    
    Returns:
        Dict with next role info or None if already at highest
    """
    current_role = determine_trader_role(current_deal_count)
    
    # Find the next role with a higher threshold
    for role in sorted(TRADER_ROLES, key=lambda x: x["threshold"]):
        if role["threshold"] > current_deal_count:
            return {
                "role_name": role["name"],
                "threshold": role["threshold"],
                "deals_needed": role["threshold"] - current_deal_count
            }
    
    return None

def format_trader_progress(current_deal_count: int) -> str:
    """
    Format a user's trader role progress as a string.
    
    Returns:
        Formatted progress string
    """
    current_role = determine_trader_role(current_deal_count)
    next_role = get_next_role_info(current_deal_count)
    
    if not current_role:
        if next_role:
            return f"**No trader role yet** (Need {next_role['deals_needed']} more deals for {next_role['role_name']})"
        else:
            return "**No trader role** (0 deals completed)"
    
    progress = f"**Current:** {current_role['name']} ({current_deal_count} deals)"
    
    if next_role:
        progress += f"\n**Next:** {next_role['role_name']} (Need {next_role['deals_needed']} more deals)"
    else:
        progress += f"\n**Status:** Maximum rank achieved! 🏆"
    
    return progress

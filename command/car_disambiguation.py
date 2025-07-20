import discord
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_mysql import resolve_car_shortcode

class CarDisambiguationView(discord.ui.View):
    def __init__(self, matches, original_input, user_id, callback_func):
        super().__init__(timeout=60)
        self.matches = matches
        self.original_input = original_input
        self.user_id = user_id
        self.callback_func = callback_func

        # Create select menu with car options
        options = []
        for i, car_name in enumerate(matches):
            options.append(discord.SelectOption(
                label=car_name,
                value=str(i),
                description=f"Select {car_name}"
            ))

        self.car_select = discord.ui.Select(
            placeholder=f"Multiple cars match '{original_input}'. Please choose one:",
            options=options,
            custom_id="car_disambiguation_select"
        )
        self.car_select.callback = self.select_callback
        self.add_item(self.car_select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the person who initiated this command can make this selection.",
                ephemeral=True
            )
            return

        selected_index = int(self.car_select.values[0])
        selected_car = self.matches[selected_index]

        # Disable the view first
        for item in self.children:
            item.disabled = True

        # Update the message to show the selection
        embed = discord.Embed(
            title="✅ Car Selected",
            description=f"You selected: **{selected_car}**",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=self)

        # Call the callback function with the selected car
        await self.callback_func(interaction, selected_car)

    async def on_timeout(self):
        # Disable all items when timeout occurs
        for item in self.children:
            item.disabled = True

def create_disambiguation_embed(matches, original_input):
    """Create an embed for car disambiguation"""
    embed = discord.Embed(
        title="🚗 Multiple Cars Found",
        description=f"The shortcode **'{original_input}'** matches multiple cars. Please select the one you want:",
        color=discord.Color.blue()
    )

    cars_list = "\n".join([f"• {car}" for car in matches])
    embed.add_field(name="Matching Cars:", value=cars_list, inline=False)

    return embed

async def handle_car_disambiguation(interaction, car_input, user_id, proceed_callback):
    """Handle car name disambiguation with user selection"""

    # Resolve the car shortcode and get matches
    display_name, original_input, matches = resolve_car_shortcode(car_input)
    print(f"Car disambiguation for '{car_input}': display_name='{display_name}', original_input='{original_input}', matches={matches}")

    # If no matches found, proceed with original input
    if not matches:
        await proceed_callback(interaction, display_name)
        return

    # If only one match found, proceed with that match
    if len(matches) == 1:
        await proceed_callback(interaction, matches[0])
        return

    # Multiple matches found - show disambiguation menu
    view = CarDisambiguationView(matches, original_input, user_id, proceed_callback)

    # Create embed
    embed = discord.Embed(
        title="🚗 Multiple Cars Found",
        description=f"I found multiple cars matching **'{original_input}'**. Please select the correct one:",
        color=discord.Color.blue()
    )

    # Add options to embed (matches is now a list of car names)
    for i, car_name in enumerate(matches[:10], 1):
        embed.add_field(
            name=f"{i}. {car_name}",
            value="Click the dropdown below to select",
            inline=False
        )

    # Send the disambiguation message
    try:
        # Check if we can still respond to the original interaction
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            # If the interaction is already done, use followup
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    except Exception as e:
        print(f"Error sending disambiguation message: {e}")
        # Fallback - proceed with original name
        await proceed_callback(interaction, display_name)
import discord
from discord.ext import commands

# Define a simple view with two buttons, confirm and cancel
class Confirm(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None
        self.user = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.response.send_message("Confirming", ephemeral=True)
        self.value = True
        self.user = interaction.user
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Cancelling", ephemeral=True)
        self.value = False
        self.user = interaction.user
        self.stop()


# Define a view with an Unban button
class Unban(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None
        self.user = None

    @discord.ui.button(label="Unban", style=discord.ButtonStyle.red)
    async def unban(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.response.send_message("Unbanning", ephemeral=True)
        self.value = True
        self.user = interaction.user
        self.stop()


# Define a view for banning possible scams
class Scam(discord.ui.View):
    def __init__(self, url):
        super().__init__(timeout=None)
        self.value = None
        self.url = url

    @discord.ui.button(label="Ban", style=discord.ButtonStyle.green)
    async def ban(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.resposne.send_message("Banning", ephemeral=True)
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.green)
    async def cancel(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.resposne.send_message("Cancelling", ephemeral=True)
        self.value = False
        self.stop()


# Defines a custom Select containing colour options
# that the user can choose. The callback function
# of this class is called when the user changes their choice
class Dropdown(discord.ui.Select):
    def __init__(self):

        # Set the options that will be presented inside the dropdown
        options = [
            discord.SelectOption(
                label="Red", description="Your favourite colour is red", emoji="🟥"
            ),
            discord.SelectOption(
                label="Green", description="Your favourite colour is green", emoji="🟩"
            ),
            discord.SelectOption(
                label="Blue", description="Your favourite colour is blue", emoji="🟦"
            ),
        ]

        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the three options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(
            placeholder="Choose your favourite colour...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        # Use the interaction object to send a response message containing
        # the user's favourite colour or choice. The self object refers to the
        # Select object, and the values attribute gets a list of the user's
        # selected options. We only want the first one.
        await interaction.response.send_message(
            f"Your favourite colour is {self.values[0]}"
        )


class DropdownView(discord.ui.View):
    def __init__(self):
        super().__init__()

        # Adds the dropdown to our view object.
        self.add_item(Dropdown())
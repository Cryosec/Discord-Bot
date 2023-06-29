# pylint: disable=F0401, W0702, W0703, W0105, W0613, unused-variable
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import discord
from datetime import datetime
import pytz
import config

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
        super().__init__(timeout=None)
        self.value = None
        self.user = None
        self.inter = None

    @discord.ui.button(label="Unban", style=discord.ButtonStyle.red)
    async def unban(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Unbanning", ephemeral=True)
        self.value = True
        self.user = interaction.user
        self.inter = interaction
        self.stop()


# Define a view for banning possible scams
class Scam(discord.ui.View):
    def __init__(self, url):
        super().__init__(timeout=None)
        self.value = None
        self.url = url
        self.user = None
        self.inter = None

    @discord.ui.button(label="Ban", style=discord.ButtonStyle.red)
    async def ban(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Banning", ephemeral=True)
        self.value = True
        self.user = interaction.user
        self.inter = interaction
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Cancelling", ephemeral=True)
        self.value = False
        self.user = interaction.user
        self.inter = interaction
        self.stop()


class BanButton(discord.ui.Button):
    def __init__(self, button_id):
        super().__init__(
            label="Ban", style=discord.ButtonStyle.red, custom_id="ban" + button_id
        )

    async def callback(self, interaction: discord.Interaction):

        # Who pressed the button
        user = interaction.user


class StopPoll(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.value = None

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.blurple)
    async def stop_poll(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.response.send_message("Stopping poll", ephemeral=True)
        self.value = True
        self.stop()

# Define a view with an Undo button for timeouts
class Untimeout(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.value = None
        self.user = None
        self.inter = None

    @discord.ui.button(label="Undo", style=discord.ButtonStyle.red)
    async def untimeout(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Undoing timeout", ephemeral=True)
        self.value = True
        self.user = interaction.user
        self.inter = interaction
        self.stop()


class Remove(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.user = None
        self.op = None
        self.inter = None

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.red)
    async def remove(self, button: discord.ui.Button, interaction: discord.Interaction):

        owner = interaction.message.author
        role = interaction.message.guild.get_role(config.MOD_ID)

        self.user = interaction.user
        self.inter = interaction
        if owner == interaction.user or role in interaction.user.roles:
            await interaction.response.send_message(content="Removing embed...", ephemeral=True)
            self.stop()
        else:
            await interaction.response.send_message(content="You cannot do this action", ephemeral=True)

tz_TX = pytz.timezone("US/Central")
TIME_FORMAT = "%b-%d-%Y %H:%M:%S"

# Support function for timeout log event
def timeout_embed(
    bot: discord.Bot, user: discord.Member, author: discord.Member, reason: str
) -> discord.Embed:
    """Generate log embed for a user timeout event

    Args:
        user (User): The user that received the timeout
        author (User): The user that called the timeout
        reason (String): Reason for the timeout
    """

    # Generate timestamp
    now = datetime.now(tz_TX)
    dt = now.strftime(TIME_FORMAT)

    embed = discord.Embed(
        title="User timeout issued",
        description=f"User {user.name}#{user.discriminator} has been timed out by {author}.",
        colour=config.YELLOW,
    )
    embed.set_author(name=bot.user.name, icon_url=bot.user.avatar.url)
    embed.add_field(name="Reason", value=reason)
    embed.add_field(name="Timestamp", value=dt)

    return embed

# Define a persistent view for @Survivor role
class Survivor(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Join the Survivors", custom_id="survivor-join", style=discord.ButtonStyle.primary)
    async def button_add_role(self, button, interaction):

        role = interaction.guild.get_role(config.SURV_ID)

        if role not in interaction.user.roles:
            await interaction.user.add_roles(role, reason="Member pressed button in #rules channel")
            await interaction.response.send_message("Welcome to the Survivors! You can now see the DayZ channels.", ephemeral=True)
        else:
            await interaction.response.send_message("You're already a Survivor! Head down to #dayz-announcements for the most recent updates.", ephemeral=True)

    @discord.ui.button(label="Leave the Survivors", custom_id="survivor-leave", style=discord.ButtonStyle.danger)
    async def button_rem_role(self, button, interaction):

        role = interaction.guild.get_role(config.SURV_ID)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role, reason="Member pressed button in #rules channel")
            await interaction.response.send_message("Sad to see you go! You can join back any time.", ephemeral=True)
        else:
            await interaction.response.send_message("You're not a Survivor! Can't remove a role you don't have.", ephemeral=True)
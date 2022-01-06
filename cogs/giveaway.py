# pylint: disable=F0401, W0702, W0703, W0105, W0613
import discord
from discord.ext import commands
from interactions import cog_ext, SlashContext, ComponentContext
from interactions.utils.manage_commands import create_option, create_permission
from interactions.utils.manage_components import create_select, create_select_option, create_actionrow
from interactions.utils.manage_components import wait_for_component, create_button
from interactions.model import SlashCommandPermissionType, ButtonStyle
import config
import random, asyncio

# BRIEF HELP
BRIEF_GA = 'Start a giveaway event in a specified channel'

# LONG HELP
HELP_GA = """**Usage::**
`!giveaway #channel <seconds> <prize description>`

The channel must be specified with the usual hashtag mention.
Giveaway duration is in seconds, and will be displayed in the bot message.
The prize **MUST** be a description, **NOT** the actual prize as it\'s visible to everyone.

NOTE: this command is available only to some specific mods/admins
"""

class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Check if command from Moderator
    async def cog_check(self, ctx):
        if ctx.author.id in config.GA_ACCESS:
            return True
        else:
            return False

    select = create_select(
        options=[# the options in your dropdown
            create_select_option("Lab Coat", value="coat", emoji="🥼"),
            create_select_option("Test Tube", value="tube", emoji="🧪"),
            create_select_option("Petri Dish", value="dish", emoji="🧫"),
        ],
        placeholder="Choose your option",  # the placeholder text to show when no options have been chosen
        min_values=1,  # the minimum number of options a user must select
        max_values=2,  # the maximum number of options a user can select
    )


# Giveaway setup command
    @cog_ext.cog_slash(name = 'giveaway',
                    description = BRIEF_GA,
                    default_permission = False,
                    options = [
                        create_option(
                            name = 'channel',
                            description = 'Channel for the giveaway.',
                            option_type = 7,
                            required = True
                        ),
                        create_option(
                            name = 'duration',
                            description = 'Duration in minutes. Defaults to 10.',
                            option_type = 4,
                            required = True
                        ),
                        create_option(
                            name = 'prize',
                            description = 'Description of prize. Everyone can see this.',
                            option_type = 3,
                            required = True
                        )
                    ],
                    guild_ids = [config.GUILD])
    @cog_ext.permission(
        guild_id = config.GUILD,
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
    async def giveaway(self, ctx: SlashContext, channel: discord.TextChannel = None, duration: int = 10, prize: str = None):

        embed = discord.Embed(
            title = '🎉 New Giveaway! 🎉',
            color = config.GREEN)
        embed.add_field(
            name = 'Prize:',
            value = "{}".format(prize),
            inline = False)
        embed.add_field(
            name = 'Duration:',
            value = "{}m".format(duration),
            inline = False)
        embed.set_footer(text=config.FOOTER)

        # Ping everyone in channel
        #msg = await channel.send(content = ctx.message.guild.default_role, embed = embed)
        msg = await channel.send(embed = embed)
        await msg.add_reaction("🎉")

        # wait duration minutes
        await asyncio.sleep(60 * duration)
        #await asyncio.sleep(duration)

        # Refresh msg reference
        msg = await msg.channel.fetch_message(msg.id)
        winner = None

        for reaction in msg.reactions:
            if reaction.emoji == "🎉":
                users = await reaction.users().flatten()
                try:
                    users.remove(self.bot)
                except:
                    pass
                winner = random.choice(users)

        if winner is not None:
            end_embed = discord.Embed(
                title = 'Giveaway Ended!',
                description = 'Prize: {}\nWinner: {}'.format(prize, winner))
            end_embed.set_footer(text=config.FOOTER)

            await msg.edit(embed=end_embed)

            notify_embed = discord.Embed(
                title = 'Giveaway Winner Selected!',
                color = config.GREEN)
            notify_embed.add_field(
                name = 'Prize: ',
                value = "{}".format(prize),
                inline = False)
            notify_embed.add_field(
                name = 'Winner: ',
                value = "{}".format(winner.mention),
                inline = False)
            notify_embed.set_footer(text=config.FOOTER)

            await channel.send(embed=notify_embed)


    """
    @cog_ext.cog_slash(name = 'test_giveaway',
                    description = BRIEF_GA,
                    options = [],
                    default_permission = False,
                    guild_ids = [config.GUILD])
    @cog_ext.permission(
        guild_id = config.GUILD,
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
        """
    @commands.command(name='ga', brief=BRIEF_GA, help=HELP_GA)
    @commands.guild_only()
    async def giveaway2(self, ctx: SlashContext):
        """Work in progress."""

        confirm_id = str(ctx.message.author.id) + str(ctx.message.id) + "confirm"
        cancel_id = str(ctx.message.author.id) + str(ctx.message.id) + "cancel"

        channel_options = []
        guild = self.bot.get_guild(config.GUILD)
        for chan in config.GA_CHANNELS:
            channel = guild.get_channel(chan)
            channel_options.append(create_select_option(channel.name, value = str(channel.id)))

        channel_select = create_select(
            options = channel_options,
            placeholder = "Choose a channel",
            min_values = 1,
            max_values = 1,
        )

        action_row_select = create_actionrow(channel_select)
        #action_row_cancel = create_actionrow(*buttons)

        ga_message = await ctx.send("Select a channel for the giveaway", components=[action_row_select])

        select_ctx: ComponentContext = await wait_for_component(self.bot, components=action_row_select)
        #button_ctx: ComponentContext = await wait_for_component(self.bot, components=action_row_cancel)

        #if button_ctx.custom_id == c_id:
        #    await ctx.send("Canceled")
        #    return

        sel_channel = guild.get_channel(int(select_ctx.selected_options[0]))

        msg = f"""
        **Channel selected**: {sel_channel.mention}\nPlease select a duration option:"""

        duration_select = create_select(
            options = [
                create_select_option("10 Minutes", value = '10'),
                create_select_option("15 Minutes", value = '15'),
                create_select_option("20 Minutes", value = '20'),
                create_select_option("30 Minutes", value = '30'),
                create_select_option("1 Hour", value = '60'),
                create_select_option("2 Hours", value = '120')
            ],
            placeholder = "Choose an option",
            min_values = 1,
            max_values = 1
        )
        action_row_duration = create_actionrow(duration_select)

        await select_ctx.edit_origin(content = msg, components = [action_row_duration])

        duration_ctx: ComponentContext = await wait_for_component(self.bot, components=action_row_duration)

        sel_duration = int(duration_ctx.selected_options[0])

        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel

        msg2 = f"""
        **Channel selected**: {sel_channel.mention}\n**Duration selected**: {sel_duration}\nPlease type a description of the prize:"""
        await duration_ctx.edit_origin(content=msg2, components = None)

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=30)
            sel_prize = msg.content
        except asyncio.TimeoutError:
            await ga_message.edit(content="Sorry!, you didn't reply in time.")
            return

        msg_final = f"""
**Channel selected**: {sel_channel.mention}
**Duration selected**: {sel_duration}
**Prize description**: {sel_prize}
"""
        embed = discord.Embed(
            title = "Giveaway settings",
            description = msg_final,
            color = config.BLUE
        )
        embed.set_author(name = self.bot.user.name, icon_url = self.bot.user.avatar_url)

        buttons = [
            create_button(
                style = ButtonStyle.green,
                label = "Confirm",
                custom_id = confirm_id
            ),
            create_button(
                style = ButtonStyle.red,
                label = "Cancel",
                custom_id = cancel_id
            )
        ]

        action_row_confirm = create_actionrow(*buttons)
        await ctx.send(embed=embed, components=[action_row_confirm])

        button_ctx: ComponentContext = await wait_for_component(self.bot, components=action_row_confirm)

        if button_ctx.custom_id == confirm_id:
            await Giveaway.giveaway(self, ctx, sel_channel, sel_duration, sel_prize)
        elif button_ctx.custom_id == cancel_id:
            cancel_embed = discord.Embed(
                title = "Giveaway canceled."
            )
            await button_ctx.edit_origin(embed=cancel_embed, components=None)

def setup(bot):
    bot.add_cog(Giveaway(bot))


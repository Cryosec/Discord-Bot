# pylint: disable=F0401, W0702, W0703, W0105, W0613, global-statement
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import discord
import asyncio
from discord.ext import commands
from discord.commands import permissions, slash_command
from discord.ui import InputText, Modal
import config, support

POLL_CONTROL = True


class Modalpoll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def print_progress_bar(
        self,
        iteration,
        total,
        decimals=1,
        length=10,
        fill="█",
    ):
        """
        Call in a loop to create terminal progress bar
        @params:
            iteration   - Required  : current iteration (Int)
            total       - Required  : total iterations (Int)
            decimals    - Optional  : positive number of decimals in percent complete (Int)
            length      - Optional  : character length of bar (Int)
            fill        - Optional  : bar fill character (Str)
        """
        percent = ("{0:." + str(decimals) + "f}").format(
            100 * (iteration / float(total))
        )
        filledLength = int(length * iteration // total)
        bar = fill * filledLength + "-" * (length - filledLength)

        return f" `|{bar}| {percent}%` "

    class PModal(Modal):
        """Define a Modal to enter Poll information."""

        def __init__(self, ctx, bot, channel) -> None:
            super().__init__("Poll information")
            self.ctx = ctx
            self.bot = bot
            self.channel = channel
            self.add_item(InputText(label="Poll title", placeholder="Title"))
            self.add_item(InputText(label="Option 1", placeholder="Banana"))
            self.add_item(InputText(label="Option 2", placeholder="Monkey"))
            self.add_item(
                InputText(label="Option 3", placeholder="Seven", required=False)
            )
            self.add_item(
                InputText(label="Option 4", placeholder="Quesadillas", required=False)
            )
            # self.add_item(InputText(label="Option 5", placeholder="Blame Avyy"))

        async def callback(self, interaction: discord.Interaction):
            """Function called when modal is completed."""
            # Collect title and options
            # value = self.children[x].value
            values = []
            for text in self.children:
                if text.value is not None:
                    values.append(text.value)
            options = values[1:]

            await interaction.response.send_message(
                "Ok, lemme create the poll...", ephemeral=True
            )

            # Define voting emojis
            selections = [
                "\U0001F7E5",
                "\U0001F7E7",
                "\U0001F7E8",
                "\U0001F7E9",
                "\U0001F7E6",
            ]

            # Create confirmation embed
            try:
                options_embed = discord.Embed(
                    title="Poll information", description="", color=config.BLUE
                )
                options_embed.add_field(name="Title", value=values[0], inline=False)
                options_embed.add_field(
                    name="Options",
                    value="\n".join("{} - {}".format(*k) for k in zip(selections, options)),
                )
                options_embed.add_field(name="Channel", value=self.channel.mention)

                options_embed.set_footer(text=config.FOOTER)

                confirm_buttons = support.Confirm()

                msg = await self.ctx.send(
                    content="Please confirm or cancel",
                    embed=options_embed,
                    view=confirm_buttons,
                )

                confirm_msg = discord.utils.get(self.bot.cached_messages, id=msg.id)

                await confirm_buttons.wait()

                # Act on confirmation
                if confirm_buttons.value:

                    try:
                        options_embed.color = config.GREEN
                    except Exception as e:
                        print("{}: {}".format(type(e).__name__, e))

                    stop_btn = support.StopPoll()

                    await msg.edit(
                        content="Poll confirmed", embed=options_embed, view=stop_btn
                    )

                    # Define actuall poll embed
                    poll = discord.Embed(
                        title=values[0],
                        description="\n".join(
                            "{} - {}".format(*k) for k in zip(selections, options)
                        ),
                        color=config.BLUE,
                    )
                    poll.set_footer(text=config.FOOTER)

                    poll_msg = await self.channel.send(embed=poll)

                    # List of reaction emojis that will be used in the poll
                    poll_sel = []

                    # Populate reactions
                    for pos in enumerate(options):
                        poll_sel.append(selections[pos[0]])
                        await poll_msg.add_reaction(selections[pos[0]])

                    # Reactions counter
                    total = 0

                    # Copy list of the options
                    percentages = options.copy()

                    cache_msg = discord.utils.get(self.bot.cached_messages, id=poll_msg.id)

                    def check_vote(reaction, user):
                        return user != self.bot.user and str(reaction.emoji) in poll_sel

                    # Define as global
                    global POLL_CONTROL

                    # Reset to True for future polls
                    POLL_CONTROL = True

                    while POLL_CONTROL:

                        # Define tasks for the wait function
                        task_rem = asyncio.create_task(
                            self.bot.wait_for("reaction_remove", check=check_vote)
                        )
                        task_add = asyncio.create_task(
                            self.bot.wait_for("reaction_add", check=check_vote)
                        )
                        task_int = asyncio.create_task(stop_btn.wait())

                        # Wait for whatever task finishes first
                        done, _pending = await asyncio.wait(
                            [task_add, task_rem, task_int],
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        if task_int in done:
                            # Stop looping
                            POLL_CONTROL = False
                            # Clear reactions
                            await cache_msg.clear_reactions()
                            # Edit confirmation embed
                            options_embed.color = config.RED
                            await confirm_msg.edit(
                                content="Poll stopped", embed=options_embed, view=None
                            )
                            return

                        # Act on reaction_add
                        elif task_add in done:

                            # Reset total counter
                            total = 0
                            # Increase total counter
                            for react in cache_msg.reactions:
                                # Count only reactions that are part of the poll
                                if str(react.emoji) in poll_sel:
                                    total += react.count
                                    # Remove the bot first reaction
                                    total -= 1

                            try:
                                # Iterate over reactions and calculate percentages
                                for ind, react in enumerate(cache_msg.reactions):
                                    if str(react.emoji) in poll_sel:
                                        # Create a progress bar with the percentage
                                        value = Modalpoll.print_progress_bar(
                                            self,
                                            iteration=(react.count - 1),
                                            total=total,
                                            length=20,
                                        )

                                        percentages[ind] = value

                                # Edit the original message poll
                                new_embed = discord.Embed(
                                    title=values[0],
                                    description="\n".join(
                                        "{} - {} {}".format(*k)
                                        for k in zip(selections, options, percentages)
                                    ),
                                    color=config.BLUE,
                                )
                                new_embed.set_footer(text=config.FOOTER)
                                await cache_msg.edit(embed=new_embed)
                            except Exception as e:
                                await self.ctx.send("{}: {}".format(type(e).__name__, e))

                        # Act on reaction_remove
                        elif task_rem in done:

                            # Reset total counter
                            total = 0
                            # Increase total counter
                            for react in cache_msg.reactions:
                                # Count only reactions that are part of the poll
                                if str(react.emoji) in poll_sel:
                                    total += react.count
                                    # Remove the bot first reaction
                                    total -= 1

                            # Avoid division by zero by resetting the poll
                            if total <= 0:
                                total = 0   # Shouldn't this be 1?
                                await cache_msg.edit(embed=poll)
                            else:
                                # Repeat calculations
                                try:
                                    # Iterate over reactions and calculate percentages
                                    for ind, react in enumerate(cache_msg.reactions):
                                        if str(react.emoji) in poll_sel:
                                            # Create a progress bar with the percentage
                                            value = Modalpoll.print_progress_bar(
                                                self,
                                                iteration=(react.count - 1),
                                                total=total,
                                                length=20,
                                            )

                                            percentages[ind] = value

                                    # Edit the original message poll
                                    new_embed = discord.Embed(
                                        title=values[0],
                                        description="\n".join(
                                            "{} - {} {}".format(*k)
                                            for k in zip(selections, options, percentages)
                                        ),
                                        color=config.BLUE,
                                    )
                                    new_embed.set_footer(text=config.FOOTER)
                                    await cache_msg.edit(embed=new_embed)
                                except Exception as e:
                                    await self.ctx.send("{}: {}".format(type(e).__name__, e))

                # Act on poll cancellation
                else:
                    await msg.edit(embed=discord.Embed(title="Poll cancelled"), view=None)
                    return

            except Exception as e:
                await self.ctx.send("{}: {}".format(type(e).__name__, e))

    @slash_command(guild_ids=[config.GUILD], name="poll")
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def poll(
        self,
        ctx,
        channel: discord.TextChannel,
    ):
        """Generate a poll in selected channel."""

        # Create modal
        poll_modal = Modalpoll.PModal(ctx, self.bot, channel)

        # Send modal, receive options
        await ctx.interaction.response.send_modal(poll_modal)

        # Manage poll in callback?


def setup(bot):
    bot.add_cog(Modalpoll(bot))

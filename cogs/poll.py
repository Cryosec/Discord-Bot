# pylint: disable=F0401, W0702, W0703, W0105, W0613, global-statement
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import discord
import asyncio
from discord.ext import commands
from discord.commands import permissions
import config, support

POLL_CONTROL = True


class Poll(commands.Cog):
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

    @commands.command(name="poll", brief=config.BRIEF_POLL, help=config.HELP_POLL)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def poll(
        self,
        ctx,
        title: str,
        channel: discord.TextChannel,
        num: int = 2,
    ):
        """Generate a poll in selected channel."""

        if num < 2:
            await ctx.reply("A minimum of 2 options is required.")
            return
        elif num > 5:
            await ctx.reply("A maximum of 5 options are allowed.")
            return

        options = []
        selections = [
            "\U0001F7E5",
            "\U0001F7E7",
            "\U0001F7E8",
            "\U0001F7E9",
            "\U0001F7E6",
        ]

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        # Ask for the options as user input, 30s timer for each
        for x in range(num):
            await ctx.send(f"Enter option number {x}:")

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30)
                options.append(msg.content)
            except asyncio.TimeoutError:
                await ctx.send(
                    "Sorry, you didn't reply in time. Poll creation aborted."
                )
                return

        # Create confirmation embed
        try:
            options_embed = discord.Embed(
                title="Poll information", description="", color=config.BLUE
            )
            options_embed.add_field(name="Title", value=title, inline=False)
            options_embed.add_field(
                name="Options",
                value="\n".join("{} - {}".format(*k) for k in zip(selections, options)),
            )
            options_embed.add_field(name="Channel", value=channel.mention)

            options_embed.set_footer(text=config.FOOTER)

            confirm_buttons = support.Confirm()

            msg = await ctx.send(
                content="Please confirm or cancel",
                embed=options_embed,
                view=confirm_buttons,
            )

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
                    title=title,
                    description="\n".join(
                        "{} - {}".format(*k) for k in zip(selections, options)
                    ),
                    color=config.BLUE,
                )
                poll.set_footer(text=config.FOOTER)

                poll_msg = await channel.send(embed=poll)

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
                confirm_msg = discord.utils.get(self.bot.cached_messages, id=msg)

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
                                    value = Poll.print_progress_bar(
                                        self,
                                        iteration=(react.count - 1),
                                        total=total,
                                        length=20,
                                    )

                                    percentages[ind] = value

                            # Edit the original message poll
                            new_embed = discord.Embed(
                                title=title,
                                description="\n".join(
                                    "{} - {} {}".format(*k)
                                    for k in zip(selections, options, percentages)
                                ),
                                color=config.BLUE,
                            )
                            new_embed.set_footer(text=config.FOOTER)
                            await cache_msg.edit(embed=new_embed)
                        except Exception as e:
                            await ctx.send("{}: {}".format(type(e).__name__, e))

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
                            total = 0
                            await cache_msg.edit(embed=poll)
                        else:
                            # Repeat calculations
                            try:
                                # Iterate over reactions and calculate percentages
                                for ind, react in enumerate(cache_msg.reactions):
                                    if str(react.emoji) in poll_sel:
                                        # Create a progress bar with the percentage
                                        value = Poll.print_progress_bar(
                                            self,
                                            iteration=(react.count - 1),
                                            total=total,
                                            length=20,
                                        )

                                        percentages[ind] = value

                                # Edit the original message poll
                                new_embed = discord.Embed(
                                    title=title,
                                    description="\n".join(
                                        "{} - {} {}".format(*k)
                                        for k in zip(selections, options, percentages)
                                    ),
                                    color=config.BLUE,
                                )
                                new_embed.set_footer(text=config.FOOTER)
                                await cache_msg.edit(embed=new_embed)
                            except Exception as e:
                                await ctx.send("{}: {}".format(type(e).__name__, e))

            # Act on poll cancellation
            else:
                await msg.edit(embed=discord.Embed(title="Poll cancelled"), view=None)
                return

        except Exception as e:
            await ctx.send("{}: {}".format(type(e).__name__, e))


def setup(bot):
    bot.add_cog(Poll(bot))

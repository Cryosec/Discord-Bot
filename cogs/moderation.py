# pylint: disable=F0401, W0702, W0703, W0105, W0613
import discord
from discord.ext import commands
import config
import support
import shelve, pytz
from datetime import datetime, timedelta
import random, typing
import re, asyncio
#import DiscordUtils
import importlib


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Check if command from Moderator
    async def cog_check(self, ctx):
        mod = ctx.guild.get_role(config.MOD_ID)
        admin = ctx.guild.get_role(config.ADMIN_ID)
        if mod in ctx.author.roles:
            return True
        elif admin in ctx.author.roles:
            return True
        else:
            return False

    @commands.command(name='ping')
    async def ping(self, ctx):
        await ctx.reply('Pong! {0} ms'.format(round(self.bot.latency * 1000, 1)))

    # !mute = mute someone with muting role
    @commands.command(name='mute', brief=config.BRIEF_MUTE, help=config.HELP_MUTE)
    @commands.guild_only()
    async def mute(self, ctx, member: typing.Optional[discord.Member] = None, *, duration: str = 'a'):

        channel = ctx.guild.get_channel(config.LOG_CHAN)
        role = ctx.guild.get_role(config.MUTE_ID)

        if 'a' in duration:

            await member.add_roles(role)

            embed = discord.Embed(title = 'Muting issued!',
                            description = 'No duration specified. Muting indefinitely.',
                            colour=config.YELLOW)
            embed.add_field(name = 'User:', value = f'{member.mention}')
            embed.add_field(name = 'Issued by:', value = f'{ctx.author.mention}')
            embed.add_field(name = 'End:', value = 'Indefinitely')
            embed.set_footer(text=config.FOOTER)

            await channel.send(content=None, embed=embed)

        else:
            tz_TX = pytz.timezone('US/Central')
            now = datetime.now(tz_TX)
            end = now
            delta = timedelta(0)
            mods = re.findall(r'([0-9]+?[wdhms])+?', duration)

            if not mods:
                await ctx.reply('**ERROR**: `duration` format is incorrect. Use `!help mute` for more information on the correct format.')
                return

            dur = ''
            for x in mods:
                if 'w' in x:
                    y = x[0:-1]
                    end = end + timedelta(weeks=int(y))
                    delta = delta + timedelta(weeks=int(y))
                    dur = dur + y + ' weeks '
                elif 'd' in x:
                    y = x[0:-1]
                    end = end + timedelta(days=int(y))
                    delta = delta + timedelta(days=int(y))
                    dur = dur + y + ' days '
                elif 'h' in x:
                    y = x[0:-1]
                    end = end + timedelta(hours=int(y))
                    delta = delta + timedelta(hours=int(y))
                    dur = dur + y + ' hours '
                elif 'm' in x:
                    y = x[0:-1]
                    end = end + timedelta(minutes=int(y))
                    delta = delta + timedelta(minutes=int(y))
                    dur = dur + y + ' minutes '
                elif 's' in x:
                    y = x[0:-1]
                    end = end + timedelta(seconds=int(y))
                    delta = delta + timedelta(seconds=int(y))
                    dur = dur + y + ' seconds '

            end_string = end.strftime('%b-%d-%Y %H:%M:%S')

            t = shelve.open(config.TIMED)

            if str(member.id) in t:
                t[str(member.id)]['mute'] = True
                t[str(member.id)]['endMute'] = end_string
            else:
                t[str(member.id)] = {'ban': False, 'mute': True,'endBan': None, 'endMute': end_string}


            await member.add_roles(role)

            dur = dur[0:-1]
            embed = discord.Embed(title = 'Muting issued!',
                            description = f'A duration of `{dur}` was specified.',
                            colour=config.YELLOW)
            embed.add_field(name = 'User:', value = f'{member.mention}')
            embed.add_field(name = 'Issued by:', value = f'{ctx.author.mention}')
            embed.add_field(name = 'End:', value = end_string)
            embed.set_footer(text=config.FOOTER)

            t.close()
            await channel.send(content=None, embed=embed)

            await asyncio.sleep(int(delta.total_seconds()))
            await member.remove_roles(role)

            t = shelve.open(config.TIMED)

            if str(member.id) in t:
                del t[str(member.id)]

            t.close()

            embed = discord.Embed(title = 'Timed mute complete',
                            description = f'User {member.mention} has been unmuted automatically.',
                            colour=config.YELLOW)
            embed.set_footer(text=config.FOOTER)

            await channel.send(content=None, embed=embed)

    # !unmute = unmute, duh
    @commands.command(name='unmute' , brief=config.BRIEF_UNMUTE, help=config.HELP_UNMUTE)
    @commands.guild_only()
    async def unmute(self, ctx, member: typing.Optional[discord.Member] = None):
        role = ctx.guild.get_role(config.MUTE_ID)

        embed = discord.Embed(title = f'User {member} has been unmuted.', colour = config.BLUE)
        await ctx.reply(embed=embed)
        await member.remove_roles(role)

    # !warn = give a warning to member
    @commands.command(name='warn', brief=config.BRIEF_WARN, help=config.HELP_WARN)
    @commands.guild_only()
    async def warn(self, ctx, member: typing.Optional[discord.Member] = None, *, reason = 'Unspecified'):
        try:
            s = shelve.open(config.WARNINGS)
            if str(member.id) in s:
                tmp = s[str(member.id)]
                tmp['warnings'] = tmp.get('warnings') + 1
                tmp['reasons'].append(reason)
                s[str(member.id)] = tmp

            else:
                s[str(member.id)] = {'warnings': 1, 'kicks': 0, 'bans': 0, 'reasons': [reason], 'tag': str(member)}

            channel = ctx.guild.get_channel(config.LOG_CHAN)
            embed = discord.Embed(title = 'Warning issued!',
                                description = f'Reason: {reason}',
                                colour=config.YELLOW)
            embed.add_field(name = 'User:', value = f'{member}')
            embed.add_field(name = 'Issued by:', value = f'{ctx.author}')
            embed.add_field(name = 'Total Warnings:', value = s[str(member.id)]['warnings'])
            embed.set_footer(text=config.FOOTER)

            s.close()

            await channel.send(content=None, embed=embed)
        except:
            pass

    # !unwarn = removes last warning
    @commands.command(name='unwarn', brief=config.BRIEF_UNWARN, help=config.HELP_UNWARN)
    @commands.guild_only()
    async def unwarn(self, ctx, member: typing.Optional[discord.Member] = None):

        s = shelve.open(config.WARNINGS)
        if str(member.id) in s:
            tmp = s[str(member.id)]
            tmp['warnings'] = tmp.get('warnings') - 1
            del tmp['reasons'][-1]
            s[str(member.id)] = tmp
            s.close()
            await Moderation.status(self, ctx, member)
        else:
            s.close()
            await Moderation.status(self, ctx, member)

    # not included in !help, used for debugging reasons
    @commands.command(name='unjac')
    @commands.guild_only()
    async def unjac(self, ctx, member: typing.Optional[discord.Member] = None):

        jac = shelve.open(config.JAC)
        if str(member.id) in jac:
            del jac[str(member.id)]
        jac.close()

    # !cwarn = clear all warnings from user
    @commands.command(name='cwarn', brief=config.BRIEF_CLEAR, help=config.HELP_CLEAR)
    @commands.guild_only()
    async def cwarn(self, ctx, member: typing.Optional[discord.Member] = None):

        if member is not None:
            s = shelve.open(config.WARNINGS)
            if str(member.id) in s:
                del s[str(member.id)]
                s.close()
                await Moderation.status(self, ctx, member.id)
            else:
                s.close()
                await Moderation.status(self, ctx, member.id)
        else:
            await ctx.reply(content='User is not a Member apparently.', embed=None)

    # !status = give status on a member.
    # This includes number of warnings, kicks and bans
    @commands.command(name='status', brief=config.BRIEF_STATUS, help=config.HELP_STATUS)
    @commands.guild_only()
    async def status(self, ctx, user = None):

        if user is not None:

            user = await self.bot.fetch_user(user)
            member = ctx.guild.get_member(user.id)


            if member is not None:

                # Is nitro boosting
                if member.premium_since is not None:
                    boosting = member.premium_since.strftime('%b-%d-%Y')
                else:
                    boosting = 'Not boosting'

                # Roles
                roles = member.roles
                role_mentions = [role.mention for role in roles]
                role_list = ", ".join(role_mentions)

                s = shelve.open(config.WARNINGS)
                if str(member.id) in s:
                    embed = discord.Embed(title = f'Status of user {member}',
                                        description = '\n'.join('{}: {}'.format(*k) for k in enumerate(s[str(member.id)]['reasons'])),
                                        colour = config.GREEN)
                    embed.add_field(name = 'Warnings:', value = s[str(member.id)]['warnings'])
                    embed.add_field(name = 'Kicks:', value = s[str(member.id)]['kicks'])
                    embed.add_field(name = 'Bans:', value = s[str(member.id)]['bans'])
                    embed.add_field(name = 'Joined:', value = member.joined_at.strftime('%b-%d-%Y %H:%M:%S'))
                    embed.add_field(name = 'Created:', value = member.created_at.strftime('%b-%d-%Y %H:%M:%S'))
                    embed.add_field(name = 'Boosting since', value=boosting, inline=False)
                    embed.add_field(name = 'Roles', value = role_list, inline=False)
                    embed.set_footer(text=config.FOOTER)
                else:
                    embed = discord.Embed(title = f'Status of user {member}',
                                        description = 'No warnings issued.',
                                        colour = config.GREEN)
                    embed.add_field(name = 'Warnings:', value = '0')
                    embed.add_field(name = 'Kicks:', value = '0')
                    embed.add_field(name = 'Bans:', value = '0')
                    embed.add_field(name = 'Joined:', value = member.joined_at.strftime('%b-%d-%Y %H:%M:%S'))
                    embed.add_field(name = 'Created:', value = member.created_at.strftime('%b-%d-%Y %H:%M:%S'))
                    embed.add_field(name = 'Boosting since', value=boosting, inline=False)
                    embed.add_field(name = 'Roles', value = role_list, inline=False)

                    embed.set_footer(text=config.FOOTER)

                s.close()
                await ctx.reply(content=None, embed=embed)

            else:
                s = shelve.open(config.WARNINGS)
                if str(user.id) in s:
                    embed = discord.Embed(title = f'Status of user {user}',
                                        description = '**User is no longer in the server**\n' + '\n'.join('{}: {}'.format(*k) for k in enumerate(s[str(user.id)]['reasons'])),
                                        colour = config.GREEN)
                    embed.add_field(name = 'Warnings:', value = s[str(user.id)]['warnings'])
                    embed.add_field(name = 'Kicks:', value = s[str(user.id)]['kicks'])
                    embed.add_field(name = 'Bans:', value = s[str(user.id)]['bans'])
                    embed.add_field(name = 'Joined:', value = 'N/A')
                    embed.set_footer(text=config.FOOTER)

                    s.close()
                    await ctx.reply(content=None, embed=embed)
                else:
                    embed = discord.Embed(title = f'Status of user {user}',
                                        description = '**User is not part of the server.**',
                                        colour = config.GREEN)
                    embed.add_field(name = 'Warnings:', value = '0')
                    embed.add_field(name = 'Kicks:', value = '0')
                    embed.add_field(name = 'Bans:', value = '0')
                    embed.add_field(name = 'Joined:', value = 'N/A')
                    embed.set_footer(text=config.FOOTER)

                    await ctx.reply(content=None, embed=embed)

        else:
            await ctx.reply('Something went wrong')

    # !timers = return all current timed events
    @commands.command(name='timers')
    @commands.guild_only()
    async def show_timers(self, ctx, *, group: str = None):
        if group is None:
            t = shelve.open(config.TIMED)

            timers = []

            for user in t:

                usr = await self.bot.fetch_user(int(user))
                ban = str(t[user]['ban'])
                mute = str(t[user]['mute'])
                endMute = str(t[user]['endMute'])
                endBan = str(t[user]['endBan'])

                string = f'{usr.mention}' + '```\nBan: ' + ban + '\nMute: ' + mute + '\nendBan: ' + endBan + '\nendMute: ' + endMute + '```'

                timers.append(string)

            if not timers:
                await ctx.reply('**INFO**: There are no timers left.')
            else:

                embed = discord.Embed(title = 'Timers',
                                        description = '\n'.join('{}: {}'.format(*k) for k in enumerate(timers)),
                                        colour = config.GREEN)
                embed.set_footer(text=config.FOOTER)

                await ctx.reply(content=None, embed=embed)
    """
    # !warns = paged list of warnings
    @bot.command(name='warns', brief=config.BRIEF_WARNINGS, help=config.HELP_WARNINGS)
    async def list_warnings(self, ctx):
        warns = shelve.open(config.WARNINGS)
        embeds= []

        for entry in warns:

            user = warns[entry]['tag']
            embed = discord.Embed(title = 'Warnings list', description = f'Current user: {user}', color=config.GREEN)
            embed.add_field(name="Warnings", value = '\n'.join('{}: {}'.format(*k) for k in enumerate(warns[entry]['reasons'])))

            embeds.append(embed)

        warns.close()
        paginator = DiscordUtils.Pagination.CustomEmbedPaginator(ctx, auto_footer=True, remove_reactions=True)
        paginator.add_reaction('⏪', "back")
        paginator.add_reaction('🔐', "lock")
        paginator.add_reaction('❌', "delete")
        paginator.add_reaction('⏩', "next")

        await paginator.run(embeds)
    """
    # !delete = delete n messages from chat
    @commands.command(name='delete', brief=config.BRIEF_DELETE, help=config.HELP_DELETE)
    @commands.guild_only()
    async def delete_messages(self, ctx, n: int):

        await ctx.message.channel.purge(limit= n + 1)

        channel = ctx.guild.get_channel(config.LOG_CHAN)

        embed = discord.Embed(title = 'Bulk Message Deletion',
                            description = f'{n} messages were deleted from {ctx.channel.name} by {ctx.author.name}#{ctx.author.discriminator}',
                            colour = config.ORANGE)
        embed.set_footer(text=config.FOOTER)

        await channel.send(content=None, embed=embed)

    # !kick = kick user from server
    @commands.command(name='kick')
    @commands.guild_only()
    async def kick_user(self, ctx, member: typing.Optional[discord.Member] = None, *, reason = 'Unspecified'):

        role = ctx.guild.get_role(config.MOD_ID)
        if role in member.roles:
            await ctx.send('You cannot kick a moderator through me.')
        else:
            s = shelve.open(config.WARNINGS)

            tz_TX = pytz.timezone('US/Central')
            now = datetime.now(tz_TX)
            dt = now.strftime("%b-%d-%Y %H:%M:%S")

            # Create feedback embed
            embed = discord.Embed(title = 'User kick issued!',
                                description = f'Reason: {reason}',
                                colour = config.RED)
            embed.add_field(name = 'Issuer:', value = ctx.author.mention)
            embed.add_field(name = 'Kicked:', value = member.mention)
            embed.add_field(name = 'When:', value = dt)
            embed.set_footer(text=config.FOOTER)

            # Record kick
            if str(member.id) in s:
                tmp = s[str(member.id)]
                tmp['kicks'] = tmp.get('kicks') + 1
                tmp['reasons'].append(reason)

                s[str(member.id)] = tmp
            else:
                s[str(member.id)] = {
                    'warnings': 0,
                    'kicks': 1,
                    'bans': 0,
                    'reasons': [reason],
                    'tag': str(member)}

            s.close()

            await ctx.guild.kick(member, reason=reason)
            channel = ctx.guild.get_channel(config.LOG_CHAN)
            await channel.send(content=None, embed=embed)

    # !tempban = temporarily ban user
    @commands.command(name='tempban', brief=config.BRIEF_TEMPBAN, help=config.HELP_TEMPBAN)
    @commands.guild_only()
    async def tempban_user(self, ctx, member: typing.Optional[discord.User], duration: str = None, *, reason = 'Unspecified'):
        role = ctx.guild.get_role(config.MOD_ID)
        channel = ctx.guild.get_channel(config.LOG_CHAN)
        mem = await bot.fetch_user(member.id)

        if role in mem.roles:
            await ctx.send('You cannot ban a moderator through me.')
        else:
            if duration is None:
                await ctx.send('**ERROR**: Command format is incorrect. Use `!help tempban` for more information on the command.')
                return
            else:
                tz_TX = pytz.timezone('US/Central')
                now = datetime.now(tz_TX)
                end = now
                delta = timedelta(0)
                mods = re.findall(r'([0-9]+?[wdhms])+?', duration)

                if not mods:
                    await ctx.send('**ERROR**: `duration` format is incorrect. Use `!help mute` for more information on the correct format.')
                    return

                dur = ''
                for x in mods:
                    if 'w' in x:
                        y = x[0:-1]
                        end = end + timedelta(weeks=int(y))
                        delta = delta + timedelta(weeks=int(y))
                        dur = dur + y + ' weeks '
                    elif 'd' in x:
                        y = x[0:-1]
                        end = end + timedelta(days=int(y))
                        delta = delta + timedelta(days=int(y))
                        dur = dur + y + ' days '
                    elif 'h' in x:
                        y = x[0:-1]
                        end = end + timedelta(hours=int(y))
                        delta = delta + timedelta(hours=int(y))
                        dur = dur + y + ' hours '
                    elif 'm' in x:
                        y = x[0:-1]
                        end = end + timedelta(minutes=int(y))
                        delta = delta + timedelta(minutes=int(y))
                        dur = dur + y + ' minutes '
                    elif 's' in x:
                        y = x[0:-1]
                        end = end + timedelta(seconds=int(y))
                        delta = delta + timedelta(seconds=int(y))
                        dur = dur + y + ' seconds '

                end_string = end.strftime('%b-%d-%Y %H:%M:%S')

                t = shelve.open(config.TIMED)

                if str(member.id) in t:
                    t[str(member.id)]['ban'] = True
                    t[str(member.id)]['endBan'] = end_string
                else:
                    t[str(member.id)] = {'ban': True, 'mute': False,'endBan': end_string, 'endMute': None}

                dur = dur[0:-1]
                embed = discord.Embed(title = 'Temp Ban issued!',
                            description = f'A duration of `{dur}` was specified.',
                            colour=config.YELLOW)
                embed.add_field(name = 'User:', value = f'{member.mention}')
                embed.add_field(name = 'Issued by:', value = f'{ctx.author.mention}')
                embed.add_field(name = 'End:', value = end_string)
                embed.set_footer(text=config.FOOTER)

                await channel.send(content=None, embed=embed)

                await member.send(f'You have ben temporarily banned from Drewski\'s Operators server. The ban lasts {dur}.')

                await ctx.guild.ban(member, reason=reason, delete_message_days=0)

                await asyncio.sleep(int(delta.total_seconds()))

                embed = discord.Embed(title = 'Timed ban complete',
                            description = f'User {member.mention} has been unbanned automatically.',
                            colour=config.YELLOW)
                embed.set_footer(text=config.FOOTER)

                await channel.send(content=None, embed=embed)
                await ctx.guild.unban(member, reason='Temp ban concluded')
                del t[str(member.id)]

                t.close()

    # !ban = ban user from server
    @commands.command(name='ban')
    @commands.guild_only()
    async def ban_user(self, ctx, member: typing.Optional[discord.Member] = None, *, reason = 'Unspecified'):

        if member is None:
            await ctx.reply("No member found with ID, might not be in the server anymore.")
            return

        role = ctx.guild.get_role(config.MOD_ID)

        if role in member.roles:
            await ctx.send('You cannot ban a moderator through me.')
        else:
            s = shelve.open(config.WARNINGS)

            tz_TX = pytz.timezone('US/Central')
            now = datetime.now(tz_TX)
            dt = now.strftime("%b-%d-%Y %H:%M:%S")

            # Create feedback embed
            embed = discord.Embed(title = 'User ban issued!',
                                description = f'Reason: {reason}',
                                colour = config.RED)
            embed.add_field(name = 'Issuer:', value = ctx.author.mention)
            embed.add_field(name = 'Banned:', value = member.mention)
            embed.add_field(name = 'When:', value = dt)
            embed.set_footer(text=config.FOOTER)

            # Record ban
            if str(member.id) in s:
                tmp = s[str(member.id)]
                tmp['bans'] = tmp.get('bans') + 1
                tmp['reasons'].append(reason)

                s[str(member.id)] = tmp
            else:
                s[str(member.id)] = {
                    'warnings': 0,
                    'kicks': 0,
                    'bans': 1,
                    'reasons': [reason],
                    'tag': str(member)}

            s.close()

            await ctx.guild.ban(member, reason=reason)
            channel = ctx.guild.get_channel(config.LOG_CHAN)
            await channel.send(content=None, embed=embed)


    # !jac = get details of user from jac db
    @commands.command(name='jac')
    @commands.guild_only()
    async def jac_details(self, ctx, member: typing.Optional[discord.Member] = None):
        jac = shelve.open(config.JAC)

        if str(member.id) in jac:

            tz_TX = pytz.timezone('US/Central')
            now = datetime.now(tz_TX)
            dt = datetime.strptime(jac[str(member.id)]['date'], "%b-%d-%Y %H:%M:%S")
            dt = dt.replace(tzinfo=tz_TX)

            end = dt + timedelta(days=14)

            delta = end - now

            embed = discord.Embed(title = f"User {member}",
                                description = jac[str(member.id)]['link'],
                                colour = config.GREEN)
            embed.add_field(name = 'Timestamp',value = jac[str(member.id)]['date'])
            embed.add_field(name = 'Time left', value = str(delta), inline=False)
            embed.set_footer(text=config.FOOTER)

            await ctx.reply(content=None, embed=embed)
        else:
            await ctx.reply('User is not in the database')

        jac.close()

    # Lundy insults, this one's an inside joke
    @commands.command(name='lundy')
    @commands.guild_only()
    async def lundy(self, ctx):

        # Remove command call
        await ctx.message.channel.purge(limit = 1)

        # Get lundy object, and ping with insult
        lundy = await ctx.guild.fetch_member(config.LUNDY_ID)
        insults = config.INSULTS
        insult = random.choice(insults)
        answer = lundy.mention + ' ' + insult
        await ctx.channel.send(answer)

    # Another inside joke with a different user
    @commands.command(name="toxy")
    @commands.guild_only()
    async def toxy(self, ctx):

        await ctx.message.channel.purge(limit = 1)
        await ctx.send("Shut the fuck up, toxy")
        toxy = ctx.guild.get_member(config.TOXY_ID)
        muted = ctx.guild.get_role(config.MUTE_ID)

        await toxy.add_roles(muted)
        await asyncio.sleep(30)
        await toxy.remove_roles(muted)

    # Floppa Friday!
    @commands.command(name="floppa")
    @commands.guild_only()
    async def floppa(self, ctx, member: discord.Member):
        #await ctx.message.channel.purge(limit=1)
        await ctx.send("I am the one who flops")
        muted = ctx.guild.get_role(config.MUTE_ID)
        await member.add_roles(muted)
        await asyncio.sleep(30)
        await member.remove_roles(muted)

    # Error handling
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply('Missing arguments, type `!help <command>` for info on your command.')
        elif isinstance(error, commands.BadArgument):
            await ctx.reply('I could not find that user. Try again.')

    # Reload config.py
    @commands.command(name='reload')
    async def reload(self, ctx):
        if ctx.message.author.id == config.CRYO_ID:
            importlib.reload(config)
            importlib.reload(support)
            await ctx.reply('Switching to your side arm is always faster than reloading.')
        else:
            await ctx.reply('You\'re not Cryo, don\'t fool around.')


def setup(bot):
    bot.add_cog(Moderation(bot))

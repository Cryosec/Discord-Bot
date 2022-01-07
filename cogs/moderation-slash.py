# pylint: disable=F0401, W0702, W0703, W0105, W0613
import shelve, pytz
from datetime import datetime, timedelta
import typing
import re, asyncio
import discord
from discord.commands import slash_command, Option, permissions
from discord.ext import commands
import cogs.moderation as mod
import config

class ModerationSlash(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # /mute Command
    @slash_command(guild_ids=[config.GUILD], name='mute',default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def mute(
        self, ctx,
        member: Option(discord.Member, "Member to mute", required = True, default = None),
        duration: Option(str, "Duration of mute", required = False, default='a')
    ):
        channel = ctx.guild.get_channel(config.LOG_CHAN)
        role = ctx.guild.get_role(config.MUTE_ID)

        if 'a' in duration:

            await member.add_roles(role)
            print(f'INFO: Muting {member} indefinitely')
            await ctx.send(embed = discord.Embed(
                title = f"User {member} has been muted indefinitely",
                colour = config.YELLOW))

            embed = discord.Embed(title = 'Muting issued!',
                            description = 'No duration specified. Muting indefinitely.',
                            colour=config.YELLOW)
            embed.add_field(name = 'User:', value = f'{member.mention}')
            embed.add_field(name = 'Issued by:', value = f'{ctx.author.mention}')
            embed.add_field(name = 'End:', value = 'Indefinitely')
            embed.set_footer(text=config.FOOTER)

            await channel.respond(content=None, embed=embed)

        else:
            tz_TX = pytz.timezone('US/Central')
            now = datetime.now(tz_TX)
            end = now
            delta = timedelta(0)
            mods = re.findall(r'([0-9]+?[wdhms])+?', duration)

            if not mods:
                await ctx.respond('**ERROR**: `duration` format is incorrect.')
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
                t[str(member.id)] = {
                    'ban': False,
                    'mute': True,
                    'endBan': None,
                    'endMute': end_string}


            await member.add_roles(role)

            print(f'INFO: Timer started - User {member} has been muted for {dur}')

            await ctx.respond(embed = discord.Embed(title = f"User {member} has been muted for {dur}",
                                                colour = config.YELLOW))

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
            print(f'INFO: Timer ended - User {member} has been unmuted')
            t = shelve.open(config.TIMED)

            if str(member.id) in t:
                del t[str(member.id)]

            t.close()

            embed = discord.Embed(title = 'Timed mute complete',
                            description = f'User {member.mention} has been unmuted automatically.',
                            colour=config.YELLOW)
            embed.set_footer(text=config.FOOTER)

            await channel.send(content=None, embed=embed)


    # /unmute Command
    @slash_command(guild_ids=[config.GUILD], name='unmute',default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def unmute(
        self, ctx,
        member: Option(discord.Member, "Member to unmute", required = True, default = None)
    ):

        if member is not None:
            role = ctx.guild.get_role(config.MUTE_ID)
            await member.remove_roles(role)
            print(f'User {member} was unmuted')
            await ctx.respond(embed = discord.Embed(title = f'User {member} was unmuted.',
                                                colour = config.GREEN))


    # /ban Command
    @slash_command(guild_ids=[config.GUILD], name='ban', default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def ban_user(
        self, ctx,
        member: Option(discord.Member, "Member to ban", required = True),
        reason: Option(str, "Reason for ban", required = False, default = None)
    ):

        if member is None:
            await ctx.respond("No member found with ID, might not be in the server anymore.")
            return

        role = ctx.guild.get_role(config.MOD_ID)

        if role in member.roles:
            await ctx.respond('You cannot ban a moderator through me.')
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
            print(f'INFO: User {member} was banned')
            await ctx.respond(embed = discord.Embed(title=f"User {member} was banned from the Server.",
                                                colour = config.RED))
            channel = ctx.guild.get_channel(config.LOG_CHAN)
            await channel.send(content=None, embed=embed)


    # /tempban Command
    @slash_command(guild_ids=[config.GUILD], name='tempban', default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def tempban_user(
        self, ctx,
        member: Option(discord.User, "Member to ban", required = True),
        duration: Option(str, "Duration of ban", required = True, default = None),
        reason = Option(str, "Reason for ban", required = False, default = 'Unspecified')
    ):
        role = ctx.guild.get_role(config.MOD_ID)
        channel = ctx.guild.get_channel(config.LOG_CHAN)
        mem = ctx.guild.get_member(member.id)

        if role in mem.roles:
            await ctx.send('You cannot ban a moderator through me.')
        else:
            if duration is None:
                await ctx.send('**ERROR**: Command format is incorrect.')
                return
            else:
                tz_TX = pytz.timezone('US/Central')
                now = datetime.now(tz_TX)
                end = now
                delta = timedelta(0)
                mods = re.findall(r'([0-9]+?[wdhms])+?', duration)

                if not mods:
                    await ctx.send('**ERROR**: `duration` format is incorrect.')
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
                    t[str(member.id)] = {
                        'ban': True,
                        'mute': False,
                        'endBan': end_string,
                        'endMute': None}

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

                print(f'Timer started - User {member} has been temporarily banned for {dur}')

                await ctx.send(embed = discord.Embed(title = f"User {member} has ben temporarily banned for {dur}",
                                                    colour = config.RED))

                await asyncio.sleep(int(delta.total_seconds()))

                embed = discord.Embed(title = 'Timed ban complete',
                            description = f'User {member.mention} has been unbanned automatically.',
                            colour=config.YELLOW)
                embed.set_footer(text=config.FOOTER)

                await channel.send(content=None, embed=embed)
                await ctx.guild.unban(member, reason='Temp ban concluded')

                print(f'Timer ended - User {member} has been unbanned.')

                del t[str(member.id)]

                t.close()


    # /kick Command
    @slash_command(guild_ids=[config.GUILD], name='kick', default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def kick_user(
        self, ctx,
        member: Option(discord.Member, "Member to kick", required = True),
        reason = Option(str, "Reason for kick", required = False, default = "Unspecified")
    ):

        role = ctx.guild.get_role(config.MOD_ID)
        if role in member.roles:
            await ctx.send('You cannot kick a moderator through me.')
        else:
            s = shelve.open(config.WARNINGS)

            #tz_TX = pytz.timezone('US/Central')
            #now = datetime.now(tz_TX)
            #dt = now.strftime("%b-%d-%Y %H:%M:%S")

            # Create feedback embed, probably unnecessary
            #embed = discord.Embed(title = 'User kick issued!',
            #                    description = f'Reason: {reason}',
            #                    colour = config.RED)
            #embed.add_field(name = 'Issuer:', value = ctx.author.mention)
            #embed.add_field(name = 'Kicked:', value = member.mention)
            #embed.add_field(name = 'When:', value = dt)
            #embed.set_footer(text=config.FOOTER)

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

            print(f'INFO: User {member} has been kicked.')

            await ctx.send(embed = discord.Embed(title = f"User {member} was kicked from the server",
                                                colour = config.RED))

            #channel = ctx.guild.get_channel(config.LOG_CHAN)
            #await channel.send(content=None, embed=embed)


    # /status Command
    @slash_command(guild_ids=[config.GUILD], name='status', default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def status(
        self, ctx,
        user: Option(discord.User, "User to lookup", required = True)
    ):

        if user is not None:

            user = await self.bot.fetch_user(user.id)
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
                await ctx.respond(content=None, embed=embed)

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
                    await ctx.respond(content=None, embed=embed)
                else:
                    embed = discord.Embed(title = f'Status of user {user}',
                        description = '**User is not part of the server.**',
                        colour = config.GREEN)
                    embed.add_field(name = 'Warnings:', value = '0')
                    embed.add_field(name = 'Kicks:', value = '0')
                    embed.add_field(name = 'Bans:', value = '0')
                    embed.add_field(name = 'Joined:', value = 'N/A')
                    embed.set_footer(text=config.FOOTER)

                    await ctx.respond(content=None, embed=embed)

        else:
            await ctx.respond('Something went wrong')


    # /warn Command
    @slash_command(guild_ids=[config.GUILD], name='warn',default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def warn(
        self, ctx,
        member: Option(discord.Member, "Member to warn", required = True),
        reason = Option(str, "Reason of warn", required = False, default = "Unspecified")
    ):
        print(f"INFO: Warning {member}...")
        try:
            s = shelve.open(config.WARNINGS)
            if str(member.id) in s:
                tmp = s[str(member.id)]
                tmp['warnings'] = tmp.get('warnings') + 1
                tmp['reasons'].append(reason)
                s[str(member.id)] = tmp

            else:
                s[str(member.id)] = {
                    'warnings': 1,
                    'kicks': 0,
                    'bans': 0,
                    'reasons': [reason],
                    'tag': str(member)}

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
            await ctx.respond(embed = discord.Embed(
                title = f'{member} has been warned'
            ))
            print("INFO: Done.")
        except:
            print("WARNING: oof, warn command broke")


    # /unwarn command
    @slash_command(guild_ids=[config.GUILD], name='unwarn', default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def unwarn(
        self, ctx,
        member: Option(discord.Member, "Member for which to remove the last warning", required = True)
    ):

        if member is not None:
            s = shelve.open(config.WARNINGS)
            if str(member.id) in s:
                tmp = s[str(member.id)]

                if tmp['warnings'] == 0:
                    del tmp
                    await ctx.respond(embed = discord.Embed(
                        title = 'No warnings to remove.'
                    ))
                    return

                tmp['warnings'] = tmp.get('warnings') - 1
                del tmp['reasons'][-1]
                s[str(member.id)] = tmp
                s.close()
                await mod.Moderation.status(self, ctx, member.id)
            else:
                s.close()
                await mod.Moderation.status(self, ctx, member.id)

            await ctx.respond(embed = discord.Embed(
                title = f'{member} last warning has been removed.'
            ))

            log_channel = ctx.guild.get_channel(config.LOG_CHAN)
            await log_channel.send(embed = discord.Embed(
                title = f'Last warning removed from user {member}', colour = config.GREEN))
            print(f'INFO: Last warning for user {member} removed.')
        else:
            await ctx.respond(embed = discord.Embed(
                title = 'User is not part of the server', colour = config.YELLOW))

    # /cwarn Command
    @slash_command(guild_ids=[config.GUILD], name='cwarn',default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def cwarn(
        self, ctx,
        member: Option(discord.Member, "Member for which to clear all warnings", required = True)
    ):

        if member is not None:
            s = shelve.open(config.WARNINGS)
            if str(member.id) in s:
                del s[str(member.id)]
                s.close()
                await mod.Moderation.status(ctx, member.id)
            else:
                s.close()
                await mod.Moderation.status(ctx, member.id)
            await ctx.respond(embed = discord.Embed(
                title = f'Warnings cleared for user {member}', colour = config.GREEN))
            print(f'Warnings for user {member} cleared.')
        else:
            await ctx.respond(emved = discord.Embed(
                title='User is not part of the server', colour = config.YELLOW))

    # /jac Command
    @slash_command(guild_ids=[config.GUILD], name='jac', default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def jac_details(
        self, ctx,
        member: Option(discord.Member, "Member for which to show JAC status")
    ):
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

            await ctx.respond(content=None, embed=embed)
        else:
            await ctx.respond('User is not in the database')

        jac.close()


    # /unjac command
    @slash_command(guild_ids=[config.GUILD], name='unjac',default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def unjac(
        self, ctx,
        member: Option(discord.Member, "Member for which to remove the last JAC entry")
    ):

        if member is not None:
            jac = shelve.open(config.JAC)
            if str(member.id) in jac:
                del jac[str(member.id)]
            jac.close()
            await ctx.respond(embed = discord.Embed(
                title = f'JAC entry removed for user {member}', colour = config.GREEN))
        else:
            await ctx.respond(embed = discord.Embed(
                title = 'User is not part of the server', colour = config.YELLOW))

    # /timers Command
    @slash_command(guild_ids=[config.GUILD], name='timers', default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def show_timers(
        self, ctx,
        group: str = None):
        if group is None:
            t = shelve.open(config.TIMED)

            timers = []

            for user in t:

                usr = await self.bot.fetch_user(int(user))
                ban = str(t[user]['ban'])
                mute = str(t[user]['mute'])
                endMute = str(t[user]['endMute'])
                endBan = str(t[user]['endBan'])

                timers.append(
                    f'{usr.mention}' +
                    '```\nBan: ' + ban +
                    '\nMute: ' + mute +
                    '\nendBan: ' + endBan +
                    '\nendMute: ' + endMute +
                    '```')

            if not timers:
                await ctx.respond(embed = discord.Embed(
                    title = 'There are no timers left.', colour = config.YELLOW))
            else:

                embed = discord.Embed(title = 'Timers',
                    description = '\n'.join('{}: {}'.format(*k) for k in enumerate(timers)),
                    colour = config.GREEN)
                embed.set_footer(text=config.FOOTER)

                await ctx.respond(embed=embed)


    # /delete Command
    @slash_command(guild_ids=[config.GUILD], name='delete', default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def delete_messages(
        self, ctx,
        messages: Option(int, "Number of messages to delete", required = True)
    ):
        await ctx.respond("Deleteing", ephemeral = True)
        await ctx.channel.purge(limit= messages)

        channel = ctx.guild.get_channel(config.LOG_CHAN)

        embed = discord.Embed(title = 'Bulk Message Deletion',
                            description = f'{messages} messages were deleted \
                                from {ctx.channel.name} by {ctx.author.name}#{ctx.author.discriminator}',
                            colour = config.ORANGE)
        embed.set_footer(text=config.FOOTER)

        await channel.send(content=None, embed=embed)


    # /slow Command
    @slash_command(guild_ids=[config.GUILD], name='slow',default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def slowmode(
        self, ctx,
        channel: Option(discord.TextChannel, "Channel in which to set the slowmode", required = True),
        seconds: Option(int, "Number of seconds for the slowmode. 0 to remove", required = True, default = 0)
    ):
        try:
            await channel.edit(slowmode_delay = seconds)

            if seconds == 0:
                await ctx.respond(embed = discord.Embed(
                    title = f'Slowmode disabled for {channel}',
                    colour = config.GREEN
                ))
            else:
                await ctx.respond(embed = discord.Embed(
                    title = f'Slowmode for {channel} set to {seconds}',
                    colour = config.YELLOW
                ))
        except:
            print(f'Error setting slowmode for channel {channel}')

    # /timeout command
    @slash_command(guild_ids=[config.GUILD], name='timeout', default_permission = False)
    @permissions.has_any_role(config.MOD_ID, config.ADMIN_ID)
    async def timeout(
        self, ctx,
        member: Option(discord.Member, "Member to timeout", required = True),
        minutes: Option(int, "Duration in minutes for the timeout", required = True, default = 10),
        reason: Option(str, "Reason for the timeout", required = False, default = None)
    ):

        duration = timedelta(minutes=minutes)
        await member.timeout_for(duration, reason)
        await ctx.respond(f'Member {member} timed out for {minutes} minutes.')


def setup(bot):
    bot.add_cog(ModerationSlash(bot))

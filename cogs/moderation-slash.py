# pylint: disable=F0401
import discord
from discord_slash import SlashCommand, cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_permission, create_choice
from discord_slash.model import SlashCommandPermissionType
from discord.ext import commands
import config
import shelve, pytz
from datetime import datetime, timedelta
import random, typing
import re, asyncio
import DiscordUtils
import cogs.moderation as mod
import logging

class ModerationSlash(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    #logging.basicConfig(format='%(asctime)s:%(levelname)s:%(name)s: %(message)s', level=logging.INFO)

    # /mute Command
    @cog_ext.cog_slash(name="mute", 
                description = config.BRIEF_MUTE, 
                default_permission = False,
                options = [
                    create_option(
                        name = 'member',
                        description = 'Member to mute',
                        option_type = 6,
                        required = True
                    ),
                    create_option(
                        name = 'duration',
                        description = 'Duration of mute',
                        option_type = 3,
                        required = False
                    )
                ],
                guild_ids=[config.GUILD])
    @cog_ext.permission(
        guild_id = config.GUILD, 
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
    async def mute(self, ctx: SlashContext, member: typing.Optional[discord.Member] = None, *, duration: str = 'a'):
        channel = ctx.guild.get_channel(config.LOG_CHAN)
        role = ctx.guild.get_role(config.MUTE_ID)

        if 'a' in duration:
            
            await member.add_roles(role)
            print(f'Muting {member} indefinitely')
            await ctx.send(embed = discord.Embed(title = f"User {member} has been muted indefinitely",
                                                colour = config.YELLOW))
            
            embed = discord.Embed(title = 'Muting issued!',
                            description = f'No duration specified. Muting indefinitely.',
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
                await ctx.reply('**ERROR**: `duration` format is incorrect.')
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
            
            print(f'Timer started - User {member} has been muted for {dur}')

            await ctx.send(embed = discord.Embed(title = f"User {member} has been muted for {dur}",
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
            print(f'Timer ended - User {member} has been unmuted')
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
    @cog_ext.cog_slash(
        name="unmute",     
        description = config.BRIEF_UNMUTE, 
        default_permission = False,
        options = [
            create_option(
                name = 'member',
                description = 'Member to unmute',
                option_type = 6,
                required = True
            )
        ],
        guild_ids=[config.GUILD])
    @cog_ext.permission(
        guild_id = config.GUILD, 
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
    async def unmute(self, ctx: SlashContext, member: typing.Optional[discord.Member] = None):

        if member is not None:
            role = ctx.guild.get_role(config.MUTE_ID)
            await member.remove_roles(role)
            print(f'User {member} was unmuted')
            await ctx.send(embed = discord.Embed(title = f'User {member} was unmuted.',
                                                colour = config.GREEN))
        

    # /ban Command
    @cog_ext.cog_slash(
        name = 'ban',
        description = config.BRIEF_BAN,
        default_permission = False,
        options = [
            create_option(
                name = 'member',
                description = 'Member to ban',
                option_type = 6,
                required = True
            ),
            create_option(
                name = 'reason',
                description = 'Reason for ban',
                option_type = 3,
                required = False
            )
        ],
        guild_ids = [config.GUILD])
    @cog_ext.permission(
        guild_id = config.GUILD, 
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
    async def ban_user(self, ctx: SlashContext, member: typing.Optional[discord.Member] = None, *, reason = 'Unspecified'):
        
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
                s[str(member.id)] = {'warnings': 0, 'kicks': 0, 'bans': 1, 'reasons': [reason], 'tag': str(member)}
            
            s.close()

            await ctx.guild.ban(member, reason=reason)
            print(f'User {member} was banned')
            await ctx.send(embed = discord.Embed(title=f"User {member} was banned from the Server.", 
                                                colour = config.RED))
            #franky.log.info(f"User {member} was banned.")
            channel = ctx.guild.get_channel(config.LOG_CHAN)
            await channel.send(content=None, embed=embed)


    # /tempban Command
    @cog_ext.cog_slash(
        name = 'tempban',
        description = config.BRIEF_TEMPBAN,
        default_permission = False,
        options = [
            create_option(
                name = 'member',
                description = 'Member to ban',
                option_type = 6,
                required = True
            ),
            create_option(
                name = 'duration',
                description = 'Duration of ban',
                option_type = 3,
                required = True,
            ),
            create_option(
                name = 'reason',
                description = 'Reason for ban',
                option_type = 3,
                required = False
            )
        ],
        guild_ids = [config.GUILD])
    @cog_ext.permission(
        guild_id = config.GUILD, 
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
    async def tempban_user(self, ctx: SlashContext, member: typing.Optional[discord.User], duration: str = None, *, reason = 'Unspecified'):
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
    @cog_ext.cog_slash(
        name = 'kick',
        description = config.BRIEF_KICK,
        default_permission = False,
        options = [
            create_option(
                name = 'member',
                description = 'Member to kick',
                option_type = 6,
                required = True
            ),
            create_option(
                name = 'reason',
                description = 'Reason for kick',
                option_type = 3,
                required = False
            )
        ],
        guild_ids = [config.GUILD])
    @cog_ext.permission(
        guild_id = config.GUILD, 
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
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
                s[str(member.id)] = {'warnings': 0, 'kicks': 1, 'bans': 0, 'reasons': [reason], 'tag': str(member)}
            
            s.close()

            await ctx.guild.kick(member, reason=reason)

            print(f'User {member} has been kicked.')

            await ctx.send(embed = discord.Embed(title = f"User {member} was kicked from the server",
                                                colour = config.RED))

            channel = ctx.guild.get_channel(config.LOG_CHAN)
            await channel.send(content=None, embed=embed)


    # /status Command
    @cog_ext.cog_slash(
        name = 'status',
        description = config.BRIEF_STATUS,
        default_permission = False,
        options = [
            create_option(
                name = 'user',
                description = 'User to lookup',
                option_type = 6,
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
    async def status(self, ctx, user: typing.Optional[discord.User] = None):

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


    # /warn Command
    @cog_ext.cog_slash(
        name = 'warn',
        description = config.BRIEF_WARN,
        default_permission = False,
        options = [
            create_option(
                name = 'member',
                description = 'Member to warn',
                option_type = 6,
                required = True
            ),
            create_option(
                name = 'reason',
                description = 'Reason of warn',
                option_type = 3,
                required = False
            ),
        ],
        guild_ids = [config.GUILD])
    @cog_ext.permission(
        guild_id = config.GUILD, 
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
    async def warn(self, ctx: SlashContext, member: typing.Optional[discord.Member] = None, *, reason = 'Unspecified'):
        print(f"Warning {member}...")
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
            await ctx.send(embed = discord.Embed(
                title = f'{member} has been warned'
            ))
            print("Done.")
        except:
            #franky.log.error(f"Error while attempting to mute {member}")
            logging.warning("oof, warn command broke")


    # /unwarn command
    @cog_ext.cog_slash(
        name="unwarn",     
        description = config.BRIEF_UNWARN, 
        default_permission = False,
        options = [
            create_option(
                name = 'member',
                description = 'Member for which to remove the last warning',
                option_type = 6,
                required = True
            )
        ],
        guild_ids=[config.GUILD])
    @cog_ext.permission(
        guild_id = config.GUILD, 
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
    async def unwarn(self, ctx: SlashContext, member: typing.Optional[discord.Member] = None):

        if member is not None:
            s = shelve.open(config.WARNINGS)
            if str(member.id) in s:
                tmp = s[str(member.id)]
                tmp['warnings'] = tmp.get('warnings') - 1
                del tmp['reasons'][-1]
                s[str(member.id)] = tmp
                s.close()
                await mod.Moderation.status(self, ctx, member)
            else:
                s.close()
                await mod.Moderation.status(self, ctx, member)

            await ctx.send(embed = discord.Embed(title = f'Last warning removed from user {member}', colour = config.GREEN))
            print(f'Last warning for user {member} removed.')
        else:
            await ctx.send(embed = discord.Embed(title = 'User is not part of the server', colour = config.YELLOW))

    # /cwarn Command
    @cog_ext.cog_slash(
        name="cwarn",     
        description = config.BRIEF_CLEAR, 
        default_permission = False,
        options = [
            create_option(
                name = 'member',
                description = 'Member for which to remove the last warning',
                option_type = 6,
                required = True
            )
        ],
        guild_ids=[config.GUILD])
    @cog_ext.permission(
        guild_id = config.GUILD, 
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
    async def cwarn(self, ctx: SlashContext, member: typing.Optional[discord.Member] = None):
        
        if member is not None:
            s = shelve.open(config.WARNINGS)
            if str(member.id) in s:
                del s[str(member.id)]
                s.close()
                await mod.Moderation.status(self, ctx, member.id)
            else:
                s.close()
                await mod.Moderation.status(self, ctx, member.id)
            await ctx.send(embed = discord.Embed(title = f'Warnings cleared for user {member}', colour = config.GREEN))
            print(f'Warnings for user {member} cleared.')
        else:
            await ctx.reply(emved = discord.Embed(title='User is not part of the server', colour = config.YELLOW))

    # /jac Command
    @cog_ext.cog_slash(
        name="jac",     
        description = config.BRIEF_JAC, 
        default_permission = False,
        options = [
            create_option(
                name = 'member',
                description = 'Member for which to show JAC status',
                option_type = 6,
                required = True
            )
        ],
        guild_ids=[config.GUILD])
    @cog_ext.permission(
        guild_id = config.GUILD, 
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
    async def jac_details(self, ctx: SlashContext, member: typing.Optional[discord.Member] = None):
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

            await ctx.send(content=None, embed=embed)
        else:
            await ctx.send('User is not in the database')

        jac.close()


    # /unjac command
    @cog_ext.cog_slash(
        name="unjac",     
        description = "Remove last JAC entry for user", 
        default_permission = False,
        options = [
            create_option(
                name = 'member',
                description = 'Member for which to remove the last JAC entry',
                option_type = 6,
                required = True
            )
        ],
        guild_ids=[config.GUILD])
    @cog_ext.permission(
        guild_id = config.GUILD, 
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
    async def unjac(self, ctx: SlashContext, member: typing.Optional[discord.Member] = None):

        if member is not None:
            jac = shelve.open(config.JAC)
            if str(member.id) in jac:
                del jac[str(member.id)]
            jac.close()
            await ctx.send(embed = discord.Embed(title = f'JAC entry removed for user {member}', colour = config.GREEN))
        else:
            await ctx.send(embed = discord.Embed(title = f'User is not part of the server', colour = config.YELLOW))

    # /timers Command
    @cog_ext.cog_slash(
        name = 'timers',
        description = config.BRIEF_TIMERS,
        default_permission = False,
        guild_ids = [config.GUILD]
    )
    @cog_ext.permission(
        guild_id = config.GUILD, 
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
    async def show_timers(self, ctx: SlashContext, *, type: str = None):
        if type is None:
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
                await ctx.send(embed = discord.Embed(title = 'There are no timers left.', colour = config.YELLOW))
            else:

                embed = discord.Embed(title = 'Timers',
                                        description = '\n'.join('{}: {}'.format(*k) for k in enumerate(timers)),
                                        colour = config.GREEN)
                embed.set_footer(text=config.FOOTER)

                await ctx.send(embed=embed)


    # /delete Command
    @cog_ext.cog_slash(
        name="delete",     
        description = config.BRIEF_DELETE, 
        default_permission = False,
        options = [
            create_option(
                name = 'messages',
                description = 'Number of messages to delete',
                option_type = 4,
                required = True
            )
        ],
        guild_ids=[config.GUILD])
    @cog_ext.permission(
        guild_id = config.GUILD, 
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ])
    async def delete_messages(self, ctx, messages: int):

        await ctx.channel.purge(limit= messages)

        channel = ctx.guild.get_channel(config.LOG_CHAN)
        
        embed = discord.Embed(title = 'Bulk Message Deletion', 
                            description = f'{messages} messages were deleted from {ctx.channel.name} by {ctx.author.name}#{ctx.author.discriminator}',
                            colour = config.ORANGE)
        embed.set_footer(text=config.FOOTER)
        
        await channel.send(content=None, embed=embed)


    # /slow Command
    @cog_ext.cog_slash(
        name = 'slow',
        description = config.BRIEF_SLOW,
        default_permission = False,
        options = [
            create_option(
                name = 'channel',
                description = 'Channel in which to set the slowmode',
                option_type = 7,
                required = True
            ),
            create_option(
                name = 'seconds',
                description = 'Number of seconds for the slowmode. 0 to remove',
                option_type = 4,
                required = True,
            )
        ],
        guild_ids = [config.GUILD]
    )
    @cog_ext.permission(
        guild_id = config.GUILD,
        permissions = [
            create_permission(config.MOD_ID, SlashCommandPermissionType.ROLE, True),
            create_permission(config.ADMIN_ID, SlashCommandPermissionType.ROLE, True),
        ]
    )
    async def slowmode(self, ctx: SlashContext, channel: discord.TextChannel, seconds: int):
        try:
            await channel.edit(slowmode_delay = seconds)
            
            if seconds == 0:
                await ctx.send(embed = discord.Embed(
                    title = f'Slowmode disabled for {channel}',
                    colour = config.GREEN
                ))
            else:
                await ctx.send(embed = discord.Embed(
                    title = f'Slowmode for {channel} set to {seconds}',
                    colour = config.YELLOW
                ))
        except:
            print(f'Error setting slowmode for channel {channel}')

def setup(bot):
    bot.add_cog(ModerationSlash(bot))
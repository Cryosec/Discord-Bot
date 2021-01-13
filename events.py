import discord
from discord.ext import commands
from datetime import datetime
import pytz, shelve
import config
import re


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):

        tz_TX = pytz.timezone('US/Central')
        now = datetime.now(tz_TX)
        dt = now.strftime("%b-%d-%Y %H:%M:%S")

        entry = await guild.fetch_ban(user)

        s = shelve.open(config.WARNINGS)
        if str(user.id) in s:
            tmp = s[str(user.id)]
            tmp['bans'] = tmp.get('bans') + 1
            tmp['reasons'].append(entry.reason)

            s[str(user.id)] = tmp
        else:
            if entry.reason is None:
                s[str(user.id)] = {'warnings': 0, 'kicks': 0, 'bans': 1, 'reasons': ['Ban: No reason specified'], 'tag': str(user)}
            else:
                s[str(user.id)] = {'warnings': 0, 'kicks': 0, 'bans': 1, 'reasons': ['Ban:' + entry.reason], 'tag': str(user)}
            
        s.close()

        author = None

        # Read audit logs
        async for log in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if log.target == entry.user:
                author = log.user

        embed = discord.Embed(title = 'User Ban',
                              description = f'User {user.name}#{user.discriminator} was banned from the Server by {author}.',
                              colour=config.RED)
        embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar_url)
        embed.add_field(name="Reason", value=entry.reason, inline=False)
        embed.add_field(name='Timestamp', value=dt)
        
        channel = guild.get_channel(config.LOG_CHAN)

        await channel.send(content=None, embed = embed)


    # But there is no on_member_kick. oof
    @commands.Cog.listener()
    async def on_member_remove(self, member):

        tz_TX = pytz.timezone('US/Central')
        now = datetime.now(tz_TX)
        dt = now.strftime("%b-%d-%Y %H:%M:%S")

        guild = member.guild

        author = None

        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
            if entry.target == member:
                author = entry.user

                embed = discord.Embed(title = 'User Kick',
                                    description = f'User {member.name}#{member.discriminator} was kicked from the server by {author}.',
                                    colour=config.RED)
                embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar_url)
                embed.add_field(name="Reason", value=entry.reason)
                embed.add_field(name='Timestamp', value=dt)
                
                channel = guild.get_channel(config.LOG_CHAN)

                await channel.send(content=None, embed = embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        # Message scanning happens here
        if int(message.channel.id) == config.CLAN_CHAN:
            role = message.guild.get_role(config.MOD_ID)
            botrole = message.guild.get_role(config.BOT_ID)
            
            # Don't do anything if moderator sent message
            if role in message.author.roles:
                return
            # Don't do anything if bot (self) is talking
            if botrole in message.author.roles:
                return
            # Save entries in JAC db, check if existence
            jac = shelve.open(config.JAC)
            s = shelve.open(config.WARNINGS)

            if str(message.author.id) in jac:
                await issue_warn(self, s, message, f"**WARNING:** {message.author.mention}, you have already posted in the last 14 days.")
                await message.delete()
            else:
                # Regexp the link
                link = re.search(r"(?P<url>https?://discord.gg/[^\s]+)", message.content)
                
                if link is None:
                    link = 'No link posted'
                else:
                    link = link.group("url")

                    # Check if link already in db
                    for key, value in jac.items():
                        if value['link'] == link:

                            # Issue warning as link already exists
                            await issue_warn(self, s, message, f"**WARNING:** {message.author.mention}, link has already been posted in the last 14 days.")
                            await message.delete()
                            s.close()
                            jac.close()
                            return

                # Get timestamp
                tz_TX = pytz.timezone('US/central')
                now = datetime.now(tz_TX)
                date = now.strftime('%b-%d-%Y %H:%M:%S')

                # Add entry because wasn't there before
                tmp = {'link': link, 'date': date}
                jac[str(message.author.id)] = tmp
                jac.sync()

            s.close()
            jac.close()

        if 'discord.gg/' in message.content:
            # Whitelist drew's link
            if 'discord.gg/drewski' in message.content:
                pass
            else:
                role = message.guild.get_role(config.MOD_ID)
                # Whitelist mods, again
                if role in message.author.roles:
                    pass
                elif message.channel.id == config.CLAN_CHAN:
                    pass
                else:
                    # Create warning message
                    await message.channel.send(f'**WARNING:** {message.author.mention}, do not post invite links.')

                    reason = f'User posted invite link in {message.channel}'
                    s = shelve.open(config.WARNINGS)
                    if str(message.author.id) in s:
                        tmp = s[str(message.author.id)]
                        tmp['warnings'] = tmp.get('warnings') + 1
                        tmp['reasons'].append(reason)

                        s[str(message.author.id)] = tmp

                        s.close()
                    else:
                        s[str(message.author.id)] = {'warnings': 1, 'kicks': 0, 'bans': 0, 'reasons': [reason], 'tag': str(message.author)}
                        s.close()

                    # Generate log embed
                    embed = discord.Embed(title = 'Warning issued!',
                            description = f'Reason: {reason}',
                            colour=config.YELLOW)
                    embed.add_field(name = 'User:', value = f'{message.author}')
                    embed.add_field(name = 'Issued by:', value = f'{self.bot.user.mention}')
                    embed.add_field(name = 'Message:', value = message.content, inline=False)
                    embed.set_footer(text=config.FOOTER)

                    channel = message.guild.get_channel(config.LOG_CHAN)
                    await channel.send(content=None, embed=embed)
                    # Delete message
                    await message.delete()

        # Delete and warn for use of blacklisted (offensive, racist and all that) words
        if any(word in message.content.lower() for word in config.BLACKLIST):
            role = message.guild.get_role(config.MOD_ID)
            if role in message.author.roles:
                pass
            else:
                await message.channel.send(f'**WARNING:** {message.author.mention}, Use of offensive terms is prohibited.')

                reason = f'User sent prohibited word in {message.channel}'
                s = shelve.open(config.WARNINGS)
                if str(message.author.id) in s:
                    tmp = s[str(message.author.id)]
                    tmp['warnings'] = tmp.get('warnings') + 1
                    tmp['reasons'].append(reason)

                    s[str(message.author.id)] = tmp

                    s.close()
                else:
                    s[str(message.author.id)] = {'warnings': 1, 'kicks': 0, 'bans': 0, 'reasons': [reason], 'tag': str(message.author)}
                    s.close()

                # Generate log embed
                embed = discord.Embed(title = 'Warning issued!',
                        description = f'Reason: {reason}',
                        colour=config.YELLOW)
                embed.add_field(name = 'User:', value = f'{message.author}')
                embed.add_field(name = 'Issued by:', value = f'{self.bot.user.name}')
                embed.add_field(name = 'Message:', value = message.content, inline=False)
                embed.set_footer(text=config.FOOTER)

                channel = message.guild.get_channel(config.LOG_CHAN)
                await channel.send(content=None, embed=embed)
                # Delete message
                await message.delete()

def setup(bot):
    bot.add_cog(Events(bot))

async def issue_warn(self, s, message, warning):
    # Notify and warn user
    await message.channel.send(warning)
    reason = f"User violated 14-day wait period in {message.channel}"

    
    if str(message.author.id) in s:
        tmp = s[str(message.author.id)]
        tmp['warnings'] = tmp.get('warnings') + 1
        tmp['reasons'].append(reason)

        s[str(message.author.id)] = tmp

        # Check if multiple 14-days violation warnings
        count = 0
        for warn in s[str(message.author.id)]['reasons']:
            if 'User violated 14-day wait period' in warn:
                count = count + 1

                # If second violation, kick from the server
                if count == 2:
                    reason = 'Kick: Multiple violations of 14-day rule in JAC'

                    tmp = s[str(message.author.id)]
                    tmp['kicks'] = tmp.get('kicks') + 1
                    tmp['reasons'].append(reason)

                    s[str(message.author.id)] = tmp
                    
                    await message.author.send('You have been kicked from Drewski\'s Operators server for violating the 14-day wait period for clan ads multiple times.')
                    await message.guild.kick(message.author, reason=reason)

        s.sync()
    else:
        s[str(message.author.id)] = {'warnings': 1, 'kicks': 0, 'bans': 0, 'reasons': [reason], 'tag': str(message.author)}
        s.sync()

    # Generate log embed
    embed = discord.Embed(title = 'Warning issued!',
            description = f'Reason: {reason}',
            colour=config.YELLOW)
    embed.add_field(name = 'User:', value = f'{message.author}')
    embed.add_field(name = 'Issued by:', value = f'{self.bot.user.mention}')
    embed.add_field(name = 'Message:', value = '{Clan Advertisment}', inline=False)
    embed.set_footer(text=config.FOOTER)

    channel = message.guild.get_channel(config.LOG_CHAN)
    await channel.send(content=None, embed=embed)
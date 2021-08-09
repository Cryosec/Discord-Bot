# pylint: disable=F0401
import discord
import logging
from discord.ext import commands
from datetime import datetime
import pytz, shelve
import config
import re
import asyncio


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reacts = ['❌', '✅']

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
        async for log in guild.audit_logs(limit=3, action=discord.AuditLogAction.ban):
            if log.target == user:
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
                
                logging.info(f"JAC Warning issued to {message.author.name}#{message.author.discriminator}")
            else:
                # Regexp the link
                link = re.search(r"(?P<url>[https?://]*discord.gg/[^\s]+)", message.content)
                
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

                            logging.info(f"JAC Warning issued to {message.author.name}#{message.author.discriminator}")

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

        # Find if .ru urls in message - CS:GO spam filter
        ru_link = re.search(r"(?P<url>https?://[^\s]+)", message.content)

        if ru_link is not None:

            logging.info("SPAM FILTER: Intercepted link - " + ru_link.group("url"))
            if any(x in ru_link.group("url") for x in config.SCAMLIST):

                logging.warning("SPAM FILTER: Intercepted link is in SCAMLIST.")
                #await message.author.add_roles(config.MUTE_ID)
                
                await message.delete()

                if ru_link.group("url") not in config.SCAM:
                    config.SCAM.append(ru_link.group("url"))

                    # TODO: create embed and add reactions for a mod to ban
                    
                    embed = discord.Embed(title = "Possible scam - manual review",
                                        description = "Review the blocked message ",
                                        colour = config.RED)
                    embed.add_field(name = 'Suspicious message', value = message.content, inline=False)                    
                    embed.add_field(name = 'Suspicious link', value = ru_link.group("url"))
                    embed.add_field(name = 'Author', value = message.author.mention)
                    embed.set_footer(text=config.FOOTER)

                    channel = message.guild.get_channel(config.LOG_CHAN)
                    manual_check = await channel.send(embed=embed)

                    for emoji in self.reacts:
                        try:
                            await manual_check.add_reaction(emoji)
                        except:
                            pass

                    # This might not work with multiple messages blocked
                    def check(reaction, user):
                        return reaction.emoji in self.reacts and reaction.message.id == manual_check.id and user.id != self.bot.user.id

                    reaction, react_user = await self.bot.wait_for('reaction_add', check = check)

                    # if user reacts with ✅
                    if str(reaction.emoji) == self.reacts[1]:
                        
                        for react in manual_check.reactions:
                            
                            if react.message.author.id == self.bot.user.id:
                                try:
                                    await manual_check.remove_reaction(str(reaction.emoji), react.message.author)
                                except:
                                    pass
                        # ban if not mod
                        modrole = message.guild.get_role(config.MOD_ID) 
                        if modrole not in message.author.roles:
                            await message.author.ban(reason = f'CS:GO spam confirmed by {react_user.mention}', delete_message_days=0)
                            config.SCAM.remove(ru_link.group("url"))
                    
                    # if user reacts with ❌
                    if str(reaction.emoji) == self.reacts[0]:
                        for react in manual_check.reactions:
                            if react.message.author.id == self.bot.user.id:
                                try:
                                    await manual_check.remove_reaction(str(reaction.emoji), react.message.author)
                                except:
                                    pass
                        config.SCAM.remove(ru_link.group("url"))

        if 'discord.gg/' in message.content:
            # Whitelist drew's link
            if 'discord.gg/drewski' in message.content:
                pass
            elif 'discord.gg/hoggit' in message.content:
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
                    logging.info(f"Invite Link Warning issued to {message.author.name}#{message.author.discriminator}")

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

                logging.info(f"Offensive word Warning issued to {message.author.name}#{message.author.discriminator}")

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

        # Embed the linked message showing content and author
        if 'discord.com/channels/' in message.content:
            link_reg = re.search(r"(?P<url>[https?://]*discord.com/channels/[^\s]+)", message.content)

            if link_reg is  None:
                return
            else:
                link_reg = link_reg.group("url")

            link = link_reg.split('/')

            server_id = int(link[4])
            channel_id = int(link[5])
            message_id = int(link[6])

            channel = message.guild.get_channel(channel_id)
            msg = await channel.fetch_message(message_id)

            embed = discord.Embed(title = f"{msg.author}",
                        description = msg.content,
                        color = config.GREEN)
            embed.set_thumbnail(url = msg.author.avatar_url)
            embed.add_field(name = 'Channel', value = msg.channel)
            embed.add_field(name = 'Time', value = msg.created_at.strftime('%b-%d-%Y %H:%M:%S') + ' UTC')
            embed.set_footer(text=config.FOOTER)

            await message.reply(embed = embed)

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
    
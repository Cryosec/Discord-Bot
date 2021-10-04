# pylint: disable=F0401
import discord
from discord.ext import commands
from datetime import datetime
import pytz, shelve
import config
import re
import asyncio
from discord_slash import SlashCommand, cog_ext, SlashContext, ComponentContext
from discord_slash.utils.manage_commands import create_option, create_permission, create_choice
from discord_slash.utils.manage_components import create_button, create_actionrow, wait_for_component
from discord_slash.model import ButtonStyle


class Events(commands.Cog):
    def __init__(self, bot):
        """Initialize Events cog."""
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        """Manage logging of member ban.
        
        Keyword arguments:
        self    -- self reference of the bot
        guild   -- Discord Guild ID
        user    -- Banned user ID
        """
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
        # For whatever reason it does not assign the author of the ban and logs "None"
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if entry.target == user:
                author = entry.user

        # Add 'unban' button under each ban embed
        buttons = [
        create_button(
            style = ButtonStyle.red,
            label = "Unban",
            custom_id = str(user.id)
        )]
        action_row = create_actionrow(*buttons)

        # Create embed to log the banning
        embed = discord.Embed(title = 'User Ban',
                              description = f'User {user.name}#{user.discriminator} was banned from the Server by {author}.',
                              colour=config.RED)
        embed.set_author(name = self.bot.user.name, icon_url = self.bot.user.avatar_url)
        embed.add_field(name="Reason", value = entry.reason, inline = False)
        embed.add_field(name='Timestamp', value = dt)
        
        channel = guild.get_channel(config.LOG_CHAN)

        await channel.send(embed = embed, components = [action_row])

        # Wait for button press on embed
        button_ctx: ComponentContext = await wait_for_component(self.bot, components=action_row)

        # Respond to button press
        if button_ctx.custom_id == str(user.id):
            
            await guild.unban(user)

            # Remove ban from db
            s = shelve.open(config.WARNINGS)
            tmp = s[str(user.id)]
            tmp['bans'] = tmp.get('bans') - 1
            del tmp['reasons'][-1]
            s[str(user.id)] = tmp
            s.close()

            # Edit ban log embed to reflect
            new_embed = discord.Embed(title = 'User ban - canceled',
                                    description = f'User {user.name}#{user.discriminator} was unbanned by {button_ctx.author.mention}',
                                    colour = config.GREEN)
            new_embed.set_author(name = self.bot.user.name, icon_url = self.bot.user.avatar_url)
            new_embed.add_field(name = 'Ban reason', value = entry.reason, inline = False)
            new_embed.add_field(name = 'Timestamp', value = now.strftime("%b-%d-%Y %H:%M:%S"))
            await button_ctx.edit_origin(embed=new_embed, components=None)



    # But there is no on_member_kick. oof
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Manage logging of member kick.
        
        Keyword arguments:
        self    -- self reference of the bot
        member  -- Kicked member ID
        """
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
        """Perform various checks on each message posted in the Guild.
        
        Keyword arguments:
        self    -- self reference of the bot
        message -- message to scan
        """

        await check_jac(self, message)
        await check_scam(self, message)
        await check_invites(self, message)
        await check_blacklist(self, message)
        await check_msg_link(self, message)

def setup(bot):
    """Add cog to the bot."""
    bot.add_cog(Events(bot))

async def check_jac(self, message):
    """Check posts inside the Join-A-Clan channel to find duplicates within the time limit.
    
    Keyword arguments:
    self    -- self reference of the bot
    message -- message to check
    
    If a message in the config.CLAN_CHAN channel is sent from the same user or contains the
    same discord invite URL within the span of 14 days, intercept the message and warn the
    user for violating the rules of the channel.
    """
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
        
async def check_scam(self, message):
    """Check each message to filter out possible scam or phishing URLs.
    
    Keyword arguments:
    self    -- self reference of the bot
    message -- message to check
    
    Each message will be scanned to check either a known scam/phishing domain or
    suspicious text/phrases that were used by userbots to spread malicious URLs.
    """
    # Find if .ru urls in message - CS:GO spam filter
    scam_link = re.search(r"(?P<url>https?://[^\s]+)", message.content)

    if scam_link is not None:

        # discord nitro scam, aggressive check
        scam_msg = message.content.replace(scam_link.group("url"), '')

        if any(y in scam_msg.lower() for y in config.SCAMTEXT):
            await message.delete()

            if scam_link.group("url") not in config.SCAM:
                config.SCAM.append(scam_link.group("url"))

                await scam_check_embed(self, message, scam_link.group("url"))

        # normal url scam check
        if any(x in scam_link.group("url") for x in config.SCAMURLS):
            
            await message.delete()

            if scam_link.group("url") not in config.SCAM:
                config.SCAM.append(scam_link.group("url"))

                await scam_check_embed(self, message, scam_link.group("url"))
    else:
        # discord nitro scam, aggressive check pt.2
        scam_msg = message.content

        if any(y in scam_msg.lower() for y in config.SCAMTEXT):
            await message.delete()

            if scam_msg not in config.SCAM:
                config.SCAM.append(scam_msg)

                await scam_check_embed(self, message, scam_msg)


async def scam_check_embed(self, message, filtered_url):
    """Generate an embed with buttons to manage possible scam or phishing messages.
    
    Keyword arguments:
    self         -- self reference of the bot
    message      --  message to check
    filtered_url -- URL that was filtered from the message
    """
    # Define a list of two buttons that will be displayed under the embed
    buttons = [
        create_button(
            style = ButtonStyle.green,
            label = "Ban",
            custom_id = "confirm"
        ),
        create_button(
            style = ButtonStyle.red,
            label = "Cancel",
            custom_id = "cancel"
        )]
    action_row = create_actionrow(*buttons)

    # Generate control embed in log channel
    embed = discord.Embed(title = "Possible scam - manual review",
                        description = "Review the blocked message ",
                        colour = config.RED)
    embed.add_field(name = 'Suspicious message', value = message.content, inline=False)                    
    embed.add_field(name = 'Suspicious link', value = filtered_url)
    embed.add_field(name = 'Author', value = message.author.mention)
    embed.add_field(name = 'Join date', value = message.author.joined_at.strftime('%b-%d-%Y %H:%M:%S'))
    embed.add_field(name = 'Creation date', value = message.author.created_at.strftime('%b-%d-%Y %H:%M:%S'))
    embed.set_footer(text=config.FOOTER)

    channel = message.guild.get_channel(config.LOG_CHAN)

    await channel.send(embed=embed, components = [action_row])
    # Wait for a mod to press a button
    button_ctx: ComponentContext = await wait_for_component(self.bot, components=action_row)

    # If mod confirms ban
    if button_ctx.custom_id == 'confirm':
        modrole = message.guild.get_role(config.MOD_ID) 
        if modrole not in message.author.roles:

            new_embed = discord.Embed(
            title = 'Possible scam - manual review completed',
            description = f'Review of the blocked message was done by {button_ctx.author.mention}',
            colour = config.GREEN
            )
            new_embed.add_field(name = 'Suspicious message', value = message.content, inline=False)                    
            new_embed.add_field(name = 'Suspicious link', value = filtered_url)
            new_embed.add_field(name = 'Author', value = message.author.mention)
            new_embed.add_field(name = 'Join date', value = message.author.joined_at.strftime('%b-%d-%Y %H:%M:%S'))
            new_embed.add_field(name = 'Creation date', value = message.author.created_at.strftime('%b-%d-%Y %H:%M:%S'))

            await button_ctx.edit_origin(embed=new_embed, components=None)
            await message.author.ban(reason = f'Spam message confirmed by {button_ctx.author.mention}', delete_message_days=0)
            try:
                config.SCAM.remove(filtered_url)
            except:
                pass

    # If mod cancels
    elif button_ctx.custom_id == 'cancel':

        new_embed = discord.Embed(
            title = 'Possible scam - manual review completed',
            description = f'Review of the blocked message was done by {button_ctx.author.mention}',
            colour = config.GREEN
        )
        new_embed.add_field(name = 'Suspicious message', value = message.content, inline=False)                    
        new_embed.add_field(name = 'Suspicious link', value = filtered_url)
        new_embed.add_field(name = 'Author', value = message.author.mention)
        new_embed.add_field(name = 'Join date', value = message.author.joined_at.strftime('%b-%d-%Y %H:%M:%S'))
        new_embed.add_field(name = 'Creation date', value = message.author.created_at.strftime('%b-%d-%Y %H:%M:%S'))

        await button_ctx.edit_origin(embed=new_embed, components=None)
        try:
            config.SCAM.remove(filtered_url)
        except:
            pass       

async def check_invites(self, message):
    """Check each message for unauthorized discord invites.
    
    Keyword arguments:
    self    -- self reference of the bot
    message -- message to check
    
    Perform a check on each message to intercept discord invites in any channel that 
    is not config.CLAN_CHAN and warn the user who posted it. If the URL is in 
    config.INVITE_WHITELIST, the message is ignored.
    """
    if 'discord.gg/' in message.content:
        # Check if in invite whitelist
        if message.content in config.INVITE_WHITELIST:
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

async def check_blacklist(self, message):
    """Check each message for blacklisted words.
    
    Keyword arguments:
    self    -- self reference of the bot
    message -- message to check
    
    Perform a check on each message to intercept blacklisted words defined in
    config.BLACKLIST and warn user who posted any.
    """
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


async def check_msg_link(self, message):
    """Check if message contains a URL to another message in the same server and embed it.
    
    Keyword arguments:
    self    -- self reference of the bot
    message -- message to check
    """
    # Embed the linked message showing content and author
    if 'discord.com/channels/' in message.content:
        # Grab the link
        link_reg = re.search(r"(?P<url>[https?://]*discord.com/channels/[^\s]+)", message.content)

        if link_reg is  None:
            return
        else:
            link_reg = link_reg.group("url")

        # Split the link into its path components 
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

async def issue_warn(self, s, message, warning):
    """Issue a warning to the specified user and create relative embed for JAC violations.
    
    Keyword arguments:
    self    -- self reference of the bot
    s       -- Shelve containing the warnings list
    message -- message that was scanned
    warning -- warning message"""
    # Notify and warn user
    await message.channel.send(warning)
    reason = f"User violated 14-day wait period in {message.channel}"

    # if the author is in the warnings database,
    # increase the relative warnings counter
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
        # and notify user in DMs
        if count == 2:
            reason = 'Kick: Multiple violations of 14-day rule in JAC'

            tmp = s[str(message.author.id)]
            tmp['kicks'] = tmp.get('kicks') + 1
            tmp['reasons'].append(reason)

            s[str(message.author.id)] = tmp
            
            await message.author.send('You have been kicked from Drewski\'s Operators server for violating the 14-day wait period for clan ads multiple times.')
            await message.guild.kick(message.author, reason=reason)
        elif count == 3:
            reason = 'Ban: Multiple kicks for violation of 14-day rule in JAC'

            tmp = s[str(message.author.id)]
            tmp['bans'] = tmp.get('bans') + 1
            tmp['reasons'].appen(reason)

            s[str(message.autorh.id)] = tmp

            await message.author.send('You have been banned from Drewski\'s Operators server for violating the 14-day wait period for clan ads multiple times.')
            

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
    
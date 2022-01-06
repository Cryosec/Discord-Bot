# pylint: disable=F0401
import  asyncio
import discord
from discord.ext import commands
from discord.commands import slash_command, Option
import config

### CONSTANTS ###

class Users(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Answer to command !help
    @commands.command(name='help')
    #@commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def help(self, ctx):

        await ctx.send(embed = discord.Embed(title = 'Type / to see the list of available commands'))


    # Answer to command !roles
    @commands.command(name='roles', brief=config.ROLES_BRIEF)
    # 1 usage every 30 seconds per channel
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def roles(self, ctx):

        role = ctx.guild.get_role(config.MOD_ID)

        if(ctx.message.channel.id != config.UCMD_CHAN) and role not in ctx.message.author.roles:
            await ctx.reply(f'Use <#{config.UCMD_CHAN}> for bot commands.')
        else:
            answer = config.ROLES_INFO

            embed = discord.Embed(title='Roles information', description=answer, colour=config.BLUE)
            embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
            embed.set_footer(text=config.FOOTER)
            await ctx.send(content=None, embed=embed)

    # Answer to command !twitch
    @commands.command(name='twitch', brief=config.TWITCH_BRIEF)
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def twitch(self, ctx):

        role = ctx.guild.get_role(config.MOD_ID)

        if(ctx.message.channel.id != config.UCMD_CHAN) and role not in ctx.message.author.roles:
            await ctx.reply(f'Use <#{config.UCMD_CHAN}> for bot commands.')
        else:
            answer = config.TWITCH_INFO

            embed = discord.Embed(title='Twitch information', url=config.TWTICH_URL, description=answer, colour=config.PURPLE)
            embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
            embed.set_footer(text=config.FOOTER)
            await ctx.send(content=None, embed=embed)


    # Answer to command !faq
    @commands.command(name="faq", brief=config.FAQ_BRIEF)
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def faq(self, ctx):

        role = ctx.guild.get_role(config.MOD_ID)

        if(ctx.message.channel.id != config.UCMD_CHAN) and role not in ctx.message.author.roles:
            await ctx.reply(f'Use <#{config.UCMD_CHAN}> for bot commands.')
        else:
            answer = config.FAQ

            embed = discord.Embed(title='Fequently Asked Questions',
                description=answer, colour=config.BLUE)
            embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
            embed.set_footer(text=config.FOOTER)
            await ctx.send(content=None, embed=embed)

    @commands.command(name="merch")
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @commands.guild_only()
    async def merch(self, ctx):
        """Return the URL with Operator Drewski's merch website."""
        await ctx.reply("You can find Operator Drewski's merch at this link:\n https://bunkerbranding.com/pages/operator-drewski")


    # Answer to command !joined
    ### CHANGED WITH !me ###
    #@commands.command(name="joined", brief=JOINED_BRIEF)
    #@commands.cooldown(1, 60, commands.BucketType.member)
    #@commands.guild_only()
    async def joined(self, ctx):
        role = ctx.guild.get_role(config.MOD_ID)

        if(ctx.message.channel.id != config.UCMD_CHAN) and role not in ctx.message.author.roles:
            await ctx.reply(f'Use <#{config.UCMD_CHAN}> for bot commands.')
        else:
            if ctx.message.author.id == config.TOXY_ID:
                await ctx.reply("Stop using this command constantly, toxy")
            elif ctx.message.author.id == config.GOOZ_ID:
                await ctx.message.author.add_roles(config.MUTE_ID)
                await ctx.reply("Stop using this command constantly, gooz")
                await asyncio.sleep(20)
                await ctx.message.author.remove_roles(config.MUTE_ID)
            else:
                timestamp = ctx.message.author.joined_at.strftime('%b-%d-%Y')
                await ctx.reply(f"You have joined the server on {timestamp}")

    # Anser to command !me
    @commands.command(name="me", brief=config.ME_BRIEF)
    @commands.cooldown(1, 86400, commands.BucketType.member)
    @commands.guild_only()
    async def me(self, ctx):
        member = ctx.message.author

        # Gooz keeps using this command every day
        if member.id == config.GOOZ_ID:
            await ctx.reply('Stop using this command, gooz')
            muted = ctx.guild.get_role(config.MUTE_ID)
            await member.add_roles(muted)
            await asyncio.sleep(30)
            await member.remove_roles(muted)
            return

        embed = discord.Embed(title=f'Information on {member.name}#{member.discriminator}',
            colour = member.colour)
        embed.set_thumbnail(url = member.avatar_url)

        # Account age
        creation_date = member.created_at.strftime('%b-%d-%Y')

        #Last join
        joined = ctx.message.author.joined_at.strftime('%b-%d-%Y')

        # Is nitro boosting
        if member.premium_since is not None:
            boosting = member.premium_since.strftime('%b-%d-%Y')
        else:
            boosting = 'Not boosting'

        # Roles
        roles = member.roles
        role_mentions = [role.mention for role in roles]
        role_list = ", ".join(role_mentions)

        embed.add_field(name='Creation date', value=creation_date, inline=True)
        embed.add_field(name='Last join', value=joined, inline=True)
        embed.add_field(name='Boosting since', value=boosting, inline=False)
        embed.add_field(name='Roles', value = role_list, inline=False)

        embed.set_author(icon_url=self.bot.user.avatar_url, name=self.bot.user.name)
        embed.set_footer(text=config.FOOTER)

        await ctx.reply(embed=embed)

def setup(bot):
    bot.add_cog(Users(bot))

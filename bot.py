"""Run with python bot.py after configuring DISCORD_TOKEN."""

import asyncio
import logging
import os
import time

import discord
from discord.ext import commands
from dotenv import load_dotenv

from wizz import WizzError, run_wizz

log = logging.getLogger(__name__)
COOLDOWN = 30.0


async def move_and_confirm(bot, member, destination, reason):
    # Register before the REST request: the gateway event can arrive first.
    confirmation = asyncio.create_task(bot.wait_for(
        "voice_state_update",
        check=lambda changed, before, after: (
            changed.id == member.id and changed.guild.id == member.guild.id
            and after.channel is not None and after.channel.id == destination.id
        ),
    ))
    try:
        await member.move_to(destination, reason=reason)
        await asyncio.wait_for(confirmation, timeout=10.0)
    finally:
        if not confirmation.done():
            confirmation.cancel()
        await asyncio.gather(confirmation, return_exceptions=True)


class WizzBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True
        intents.voice_states = True
        super().__init__(
            command_prefix="~", intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.active = {}
        self.cooldowns = {}

    async def close(self):
        # Let running wizzes restore members while the gateway is still open.
        tasks = list(self.active.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await super().close()


bot = WizzBot()


@bot.event
async def on_ready():
    log.info("Logged in as %s. Use ~wizz @UserName", bot.user)


@bot.command(ignore_extra=False)
@commands.guild_only()
async def wizz(ctx, member: discord.Member):
    """Move a member between two temporary voice rooms for five seconds."""
    if member.bot:
        await ctx.send("Mention a person rather than a bot.")
        return
    if ctx.guild.id in bot.active:
        await ctx.send("A wizz is already running in this server. Try again in a moment.")
        return
    current = time.monotonic()
    bot.cooldowns = {key: expiry for key, expiry in bot.cooldowns.items() if expiry > current}
    keys = [(ctx.guild.id, kind, user_id) for kind, user_id in (
        ("caller", ctx.author.id), ("target", member.id))]
    remaining = max((bot.cooldowns.get(key, 0) - current for key in keys), default=0)
    if remaining > 0:
        await ctx.send(f"Let the wizz cool down. Try again in {remaining:.0f} seconds.")
        return

    reason = f"Wizz requested by {ctx.author.id} for {member.id}"

    async def perform():
        return await run_wizz(
            ctx.guild, member, ctx.guild.me, reason,
            lambda person, room, why: move_and_confirm(bot, person, room, why),
        )

    task = asyncio.create_task(perform())
    bot.active[ctx.guild.id] = task
    for key in keys:
        bot.cooldowns[key] = current + COOLDOWN
    try:
        result = await task
        text = ("Wizz stopped because they left or changed voice channels."
                if result.interrupted else f"Wizz! {member.display_name} got {result.moves} nudges.")
        if result.warnings:
            text += " " + " ".join(result.warnings)
        await ctx.send(text)
    except WizzError as error:
        await ctx.send(str(error))
    finally:
        bot.active.pop(ctx.guild.id, None)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send("Use this command in a server.")
    elif isinstance(error, (commands.UserInputError, commands.MemberNotFound)):
        await ctx.send("Usage: `~wizz @UserName` — mention exactly one server member.")
    else:
        log.error("Command failed", exc_info=(type(error), error, error.__traceback__))
        await ctx.send("The command failed. Check the bot's logs and channel permissions.")


def main():
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token or token == "your_bot_token_here":
        raise SystemExit("Set DISCORD_TOKEN in .env first (see .env.example).")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    bot.run(token)


if __name__ == "__main__":
    main()

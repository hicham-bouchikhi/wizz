"""Temporary voice-channel movement with restoration and cleanup."""

import asyncio
import logging
import time
from dataclasses import dataclass, field

import discord

log = logging.getLogger(__name__)
DURATION = 5.0
INTERVAL = 1.0


class WizzError(Exception):
    """A failure that can be explained to the command's caller."""


@dataclass
class WizzResult:
    moves: int = 0
    interrupted: bool = False
    warnings: list[str] = field(default_factory=list)


def channel_id(member):
    return member.voice.channel.id if member.voice and member.voice.channel else None


async def run_wizz(guild, member, bot_member, reason, move, *,
                   now=time.monotonic, sleep=asyncio.sleep):
    """`move` must await the voice-state confirmation as well as the REST call."""
    original = member.voice.channel if member.voice else None
    if not isinstance(original, discord.VoiceChannel):
        raise WizzError("That person must already be in a regular voice channel.")
    if not bot_member.guild_permissions.manage_channels:
        raise WizzError("I need the Manage Channels permission.")
    permissions = original.permissions_for(bot_member)
    if not (permissions.view_channel and permissions.connect and permissions.move_members):
        raise WizzError("I need View Channel, Connect, and Move Members in their voice channel.")

    rooms = []
    result = WizzResult()
    failure = None
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
        bot_member: discord.PermissionOverwrite(
            view_channel=True, connect=True, manage_channels=True, move_members=True),
        member: discord.PermissionOverwrite(view_channel=True, connect=True),
    }
    try:
        # Keep these outside categories so category denials cannot block recovery.
        for suffix in ("a", "b"):
            rooms.append(await guild.create_voice_channel(
                f"wizz-{member.id}-{suffix}", overwrites=overwrites, reason=reason))

        expected = original.id
        deadline = now() + DURATION
        while now() < deadline:
            if channel_id(member) != expected:
                result.interrupted = True
                break
            destination = rooms[result.moves % 2]
            await move(member, destination, reason)
            expected = destination.id
            result.moves += 1
            remaining = deadline - now()
            if remaining > 0:
                await sleep(min(INTERVAL, remaining))
        if result.moves and channel_id(member) != expected:
            result.interrupted = True
    except Exception as error:
        log.exception("Wizz failed in guild %s", guild.id)
        failure = error
    finally:
        # Also runs on cancellation. Never pull someone back after they leave.
        room_ids = {room.id for room in rooms}
        if channel_id(member) in room_ids:
            try:
                await move(member, original, reason)
            except Exception:
                log.exception("Could not restore member %s", member.id)
                result.warnings.append("I couldn't return them to their original channel.")

        for room in rooms:
            # Deleting an occupied room would disconnect its members.
            if channel_id(member) == room.id or room.members:
                result.warnings.append(f"Room {room.id} was left in place because it is occupied.")
                continue
            try:
                await room.delete(reason=reason)
            except discord.NotFound:
                pass
            except Exception:
                log.exception("Could not delete temporary room %s", room.id)
                result.warnings.append(f"Couldn't delete temporary room {room.id}.")
    if failure:
        detail = " ".join(result.warnings)
        raise WizzError(f"Wizz couldn't finish. Check my permissions and try again. {detail}".strip()) from failure
    return result

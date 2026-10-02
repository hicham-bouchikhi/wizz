import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from wizz import WizzError, run_wizz


class Member:
    def __init__(self, member_id):
        self.id = member_id
        self.voice = None
        self.guild_permissions = SimpleNamespace(manage_channels=True)


class WizzTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch("wizz.log"))
        self.clock = 0.0
        self.member = Member(42)
        self.bot_member = Member(99)
        self.original = self.room(1)
        self.rooms = [self.room(2), self.room(3)]
        self.member.voice = SimpleNamespace(channel=self.original)
        self.original.members.append(self.member)
        self.guild = SimpleNamespace(
            id=123, default_role=object(),
            create_voice_channel=AsyncMock(side_effect=self.rooms),
        )
        self.moves = []
        self.after_sleep = None

    def room(self, room_id):
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.id = room_id
        channel.members = []
        channel.delete = AsyncMock()
        channel.permissions_for.return_value = SimpleNamespace(
            view_channel=True, connect=True, move_members=True)
        return channel

    def relocate(self, destination):
        current = self.member.voice.channel if self.member.voice else None
        if current and self.member in current.members:
            current.members.remove(self.member)
        self.member.voice = SimpleNamespace(channel=destination) if destination else None
        if destination:
            destination.members.append(self.member)

    async def move(self, member, destination, reason):
        self.moves.append(destination.id)
        self.relocate(destination)

    async def sleep(self, duration):
        self.clock += duration
        if self.after_sleep:
            self.after_sleep()

    async def run_effect(self, move=None):
        return await run_wizz(
            self.guild, self.member, self.bot_member, "test wizz", move or self.move,
            now=lambda: self.clock, sleep=self.sleep,
        )

    async def test_five_seconds_alternates_restores_and_deletes(self):
        result = await self.run_effect()
        self.assertEqual(self.moves, [2, 3, 2, 3, 2, 1])
        self.assertEqual(self.clock, 5.0)
        self.assertEqual(result.moves, 5)
        self.assertFalse(result.interrupted)
        self.assertEqual(result.warnings, [])
        for room in self.rooms:
            room.delete.assert_awaited_once()
        overwrites = self.guild.create_voice_channel.call_args.kwargs["overwrites"]
        self.assertFalse(overwrites[self.guild.default_role].connect)
        self.assertTrue(overwrites[self.member].connect)
        self.assertTrue(overwrites[self.bot_member].manage_channels)

    async def test_partial_creation_failure_deletes_first_room(self):
        self.guild.create_voice_channel.side_effect = [self.rooms[0], RuntimeError("creation failed")]
        with self.assertRaises(WizzError):
            await self.run_effect()
        self.rooms[0].delete.assert_awaited_once()
        self.rooms[1].delete.assert_not_awaited()
        self.assertEqual(self.moves, [])

    async def test_failed_move_still_restores_member(self):
        async def move(member, destination, reason):
            if destination.id == 3:
                raise RuntimeError("move denied")
            await self.move(member, destination, reason)

        with self.assertRaises(WizzError):
            await self.run_effect(move)
        self.assertEqual(self.moves, [2, 1])
        for room in self.rooms:
            room.delete.assert_awaited_once()

    async def test_disconnect_stops_without_reconnecting(self):
        self.after_sleep = lambda: self.relocate(None)
        result = await self.run_effect()
        self.assertTrue(result.interrupted)
        self.assertEqual(self.moves, [2])
        self.assertIsNone(self.member.voice)
        for room in self.rooms:
            room.delete.assert_awaited_once()

    async def test_manual_channel_change_is_preserved(self):
        other = self.room(4)
        self.after_sleep = lambda: self.relocate(other)
        result = await self.run_effect()
        self.assertTrue(result.interrupted)
        self.assertEqual(self.moves, [2])
        self.assertEqual(self.member.voice.channel.id, 4)

    async def test_failed_restoration_keeps_occupied_room(self):
        async def move(member, destination, reason):
            if destination.id == 1:
                raise RuntimeError("original room deleted")
            await self.move(member, destination, reason)

        result = await self.run_effect(move)
        self.assertTrue(result.warnings)
        self.rooms[0].delete.assert_not_awaited()
        self.rooms[1].delete.assert_awaited_once()
        self.assertEqual(self.member.voice.channel.id, 2)

    async def test_cleanup_continues_when_one_deletion_fails(self):
        self.rooms[0].delete.side_effect = RuntimeError("delete denied")
        result = await self.run_effect()
        self.assertEqual(len(result.warnings), 1)
        self.rooms[1].delete.assert_awaited_once()
        self.assertEqual(self.member.voice.channel.id, 1)

    async def test_cancellation_restores_and_cleans_up(self):
        def cancel():
            raise asyncio.CancelledError()

        self.after_sleep = cancel
        with self.assertRaises(asyncio.CancelledError):
            await self.run_effect()
        self.assertEqual(self.moves, [2, 1])
        for room in self.rooms:
            room.delete.assert_awaited_once()

    async def test_missing_permissions_do_not_create_rooms(self):
        self.original.permissions_for.return_value.move_members = False
        with self.assertRaises(WizzError):
            await self.run_effect()
        self.guild.create_voice_channel.assert_not_awaited()

    async def test_disconnected_target_does_not_create_rooms(self):
        self.relocate(None)
        with self.assertRaises(WizzError):
            await self.run_effect()
        self.guild.create_voice_channel.assert_not_awaited()

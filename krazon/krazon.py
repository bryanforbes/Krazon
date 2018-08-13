from typing import List, Optional, Any, Dict, cast
from pathlib import Path
from io import BytesIO
from hashlib import sha256

import logging
import discord
import attr
import asyncio

from discord.ext import commands
from botus_receptus.db import Bot
from botus_receptus.formatting import EmbedPaginator

from .exceptions import ClipNotFound, FilenameExists, MustBeConnected, TooManyMembers
from .context import Context, GuildContext


log = logging.getLogger(__name__)


@attr.s(slots=True, auto_attribs=True)
class GuildVoiceEntry(object):
    channel: discord.VoiceChannel
    path: str
    requester: discord.User


@attr.s(slots=True, auto_attribs=True)
class GuildVoiceState(object):
    board: 'SoundBoard'
    bot: 'Krazon'

    voice_client: Optional[discord.VoiceClient] = attr.ib(init=False)
    audio_player: asyncio.Task = attr.ib(init=False)

    next_clip: asyncio.Event = attr.ib(init=False)
    clips: List[GuildVoiceEntry] = attr.ib(init=False)
    current_clip: Optional[GuildVoiceEntry] = attr.ib(init=False)

    def __attrs_post_init__(self) -> None:
        self.__reinitialize()

    def __reinitialize(self) -> None:
        self.voice_client = None
        self.audio_player = self.bot.loop.create_task(self.__audio_player_task())
        self.next_clip = asyncio.Event(loop=self.bot.loop)
        self.clips = []
        self.current_clip = None

    @property
    def is_playing(self) -> bool:
        if self.voice_client is None:
            return False

        return self.voice_client.is_playing()

    async def __audio_player_task(self) -> None:
        while await self.next_clip.wait() and len(self.clips) > 0:
            entry = self.current_clip = self.clips.pop(0)

            if self.voice_client is None:
                self.voice_client = await entry.channel.connect()
            elif entry.channel is not self.voice_client.channel:
                await self.voice_client.move_to(entry.channel)

            source = discord.FFmpegPCMAudio(entry.path)

            self.voice_client.play(source, after=self.__play_next_clip)
            self.next_clip.clear()

        await cast(discord.VoiceClient, self.voice_client).disconnect()
        self.__reinitialize()

    def __play_next_clip(self, error: Optional[Exception]) -> None:
        self.bot.loop.call_soon_threadsafe(self.next_clip.set)

    def add_to_queue(self, channel: discord.VoiceChannel, path: str, user: discord.User) -> None:
        self.clips.append(GuildVoiceEntry(channel=channel, path=path, requester=user))

        if not self.is_playing:
            self.next_clip.set()

    def skip(self) -> None:
        if len(self.clips) == 0 and self.current_clip is None:
            return

        if self.voice_client is not None:
            self.voice_client.stop()


@attr.s(slots=True, auto_attribs=True)
class Clip(object):
    id: int
    name: str
    member_id: int
    hash: str
    filename: str

    def get_path(self, storage_path: Path) -> Path:
        return storage_path / self.hash

    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> 'Clip':
        clip = await ctx.get_clip_by_name(argument)

        if clip is None:
            raise ClipNotFound(argument)

        return cls(id=clip['id'], name=clip['name'], member_id=int(clip['member_id']), filename=clip['filename'],
                   hash=clip['hash'])


def play_checks(ctx: commands.Context) -> bool:
    author = cast(discord.Member, ctx.author)

    if author.voice is None or author.voice.channel is None:
        raise MustBeConnected()

    channel = author.voice.channel

    if isinstance(channel, discord.VoiceChannel) and channel.user_limit == len(channel.members):
        raise TooManyMembers()

    return True


@attr.s(slots=True, auto_attribs=True)
class SoundBoard(object):
    bot: 'Krazon'
    voice_states: Dict[int, GuildVoiceState] = attr.ib(init=False, default=attr.Factory(dict))
    __weakref__: Any = attr.ib(init=False, hash=False, repr=False, cmp=False)

    def __attrs_post_init__(self) -> None:
        self.storage_path.mkdir(parents=True, exist_ok=True)

    async def on_command_completion(self, ctx: Context) -> None:
        await ctx.message.delete()

    async def __error(self, ctx: Context, error: Exception) -> None:
        await ctx.message.delete()

        if isinstance(error, ClipNotFound) or isinstance(error, FilenameExists) or \
                isinstance(error, MustBeConnected) or isinstance(error, TooManyMembers):
            await ctx.send_error(error.args[0])
        elif isinstance(error, commands.BadArgument) or isinstance(error, commands.MissingRequiredArgument):
            pages = await ctx.bot.formatter.format_help_for(ctx, ctx.command)

            for page in pages:
                await ctx.send(page)
        else:
            raise error

    @property
    def storage_path(self) -> Path:
        return Path(self.bot.config.get('storage', 'path'))

    def get_voice_state(self, guild: discord.Guild) -> GuildVoiceState:
        state = self.voice_states.get(guild.id)

        if state is None:
            state = GuildVoiceState(self, self.bot)
            self.voice_states[guild.id] = state

        return state

    @commands.command()
    @commands.check(play_checks)
    @commands.guild_only()
    async def play(self, ctx: GuildContext, clip: Clip) -> None:
        state = self.get_voice_state(ctx.guild)
        channel = cast(discord.VoiceChannel, cast(discord.VoiceState, ctx.author.voice).channel)

        state.add_to_queue(channel, str(clip.get_path(self.storage_path)), cast(discord.User, ctx.author))

    @commands.command()
    @commands.guild_only()
    async def skip(self, ctx: GuildContext) -> None:
        state = self.get_voice_state(ctx.guild)

        if ctx.author != ctx.guild.owner and (state.current_clip is None or ctx.author != state.current_clip.requester):
            await ctx.send_error('You are not allowed to skip the clip')
            return

        state.skip()

    @commands.command()
    async def list(self, ctx: Context) -> None:
        clips = await ctx.get_clips()

        if len(clips) > 0:
            paginator = EmbedPaginator()

            for clip in clips:
                paginator.add_line(f'`{clip["name"]}`: {clip["filename"]}')

            for page in paginator:
                await ctx.send_response(page, title=f'Clips for {ctx.author.display_name}')
        else:
            await ctx.send_response('No clips found')

    @commands.command()
    async def add(self, ctx: Context, clip_name: str) -> None:
        clip = await ctx.get_clip_by_name(clip_name)

        if clip is not None:
            await ctx.send_error(f'A clip already exists with name `{clip_name}`')
            return

        if len(ctx.message.attachments) == 0:
            await ctx.send_error('You must attach a sound file to the message')
            return

        attachment = ctx.message.attachments[0]

        if attachment.size > 2621440:
            await ctx.send_error('There is a limit of 2.5MB on clip files')
            return

        file_buffer = BytesIO()
        await attachment.save(file_buffer)
        file_hash = sha256()
        file_hash.update(file_buffer.getvalue())

        hash_string = file_hash.hexdigest()
        file_path = self.storage_path / hash_string

        clip = await ctx.get_clip_by_hash(hash_string)

        if await ctx.get_clip_by_hash(hash_string) is None:
            file_path.write_bytes(file_buffer.getvalue())

        await ctx.insert_into(table='clips',
                              values={
                                  'name': clip_name,
                                  'member_id': str(ctx.author.id),
                                  'hash': hash_string,
                                  'filename': attachment.filename
                              })

        await ctx.send_response(f'Successfully added `{clip_name}`', delete_after=5)

    @commands.command()
    async def remove(self, ctx: Context, clip: Clip) -> None:
        file_path = clip.get_path(self.storage_path)

        await ctx.delete_from(clip.id, table='clips', where=['id = $1'])

        if await ctx.get_clip_by_hash(clip.hash) is None:
            if file_path.exists():
                file_path.unlink()

        await ctx.send_response(f'Clip `{clip.name}` removed', delete_after=5)

    @commands.command()
    async def rename(self, ctx: Context, clip: Clip, new_name: str) -> None:
        if await ctx.get_clip_by_name(new_name) is not None:
            await ctx.send_error(f'A clip already has the name `{new_name}`')
            return

        await ctx.update(clip.id, new_name, table='clips',
                         values={
                             'name': '$2'
                         },
                         where=['id = $1'])
        await ctx.send_response(f'Clip `{clip.name}` renamed to `{new_name}`', delete_after=5)

    @commands.command()
    async def share(self, ctx: Context, clip: Clip, user: discord.User, clip_name: Optional[str] = None) -> None:
        if clip_name is None:
            clip_name = clip.name

        if await ctx.get_clip_by_name(clip_name, user=user) is not None:
            await ctx.send_error(f'{user} already has a clip named `{clip_name}`')
            return

        await ctx.insert_into(table='clips',
                              values={
                                  'name': clip_name,
                                  'member_id': str(user.id),
                                  'hash': clip.hash,
                                  'filename': clip.filename
                              })

        await ctx.send_response(f'Successfully shared `{clip_name or clip.name}` '
                                f'with {user.display_name}', delete_after=5)


class Krazon(Bot[Context]):
    context_cls = Context

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        if not discord.opus.is_loaded():
            discord.opus.load_opus(self.config.get('opus', 'path'))

        self.add_cog(SoundBoard(self))

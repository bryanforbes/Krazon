from typing import List, Optional, Union, Any, Dict
from mypy_extensions import TypedDict
from datetime import datetime
from pathlib import Path

import logging
import discord
import attr
import asyncio

from discord.ext import commands
from botus_receptus import EmbedContext
from botus_receptus.db import Bot, Context as DbContext
from botus_receptus.formatting import EmbedPaginator
from botus_receptus.context import FooterData, AuthorData, FieldData


log = logging.getLogger(__name__)


class Clip(TypedDict):
    id: int
    name: str
    member_id: str
    filename: str


@attr.s(slots=True, auto_attribs=True)
class VoiceEntry(object):
    requester: discord.Member


@attr.s(slots=True, auto_attribs=True)
class VoiceState(object):
    bot: 'Krazon'
    voice_client: Optional[discord.VoiceClient] = attr.ib(init=False, default=None)
    clips: asyncio.Queue = attr.ib(init=False, default=attr.Factory(asyncio.Queue))
    current_clip: Optional[VoiceEntry] = attr.ib(init=False, default=None)


class Context(DbContext, EmbedContext):
    bot: 'Krazon'
    has_error: bool = False

    async def send_error(self, description: str, *,
                         title: Optional[str] = None,
                         footer: Optional[Union[str, FooterData]] = None,
                         thumbnail: Optional[str] = None,
                         author: Optional[Union[str, AuthorData]] = None,
                         image: Optional[str] = None,
                         timestamp: Optional[datetime] = None,
                         fields: Optional[List[FieldData]] = None,
                         tts: bool = False, file: Optional[object] = None,
                         files: Optional[List[object]] = None, delete_after: Optional[float] = None,
                         nonce: Optional[int] = None) -> discord.Message:
        self.has_error = True
        return await self.send_embed(description, color=discord.Color.red(), title=title, footer=footer,
                                     thumbnail=thumbnail, author=author, image=image, timestamp=timestamp,
                                     fields=fields, tts=tts, file=file, files=files, delete_after=delete_after,
                                     nonce=nonce)

    async def send_response(self, description: str, *,
                            title: Optional[str] = None,
                            color: Optional[Union[discord.Color, int]] = discord.Color.green(),
                            footer: Optional[Union[str, FooterData]] = None,
                            thumbnail: Optional[str] = None,
                            author: Optional[Union[str, AuthorData]] = None,
                            image: Optional[str] = None,
                            timestamp: Optional[datetime] = None,
                            fields: Optional[List[FieldData]] = None,
                            tts: bool = False, file: Optional[object] = None,
                            files: Optional[List[object]] = None, delete_after: Optional[float] = None,
                            nonce: Optional[int] = None) -> discord.Message:
        return await self.send_embed(description, color=color, title=title, footer=footer,
                                     thumbnail=thumbnail, author=author, image=image, timestamp=timestamp,
                                     fields=fields, tts=tts, file=file, files=files, delete_after=delete_after,
                                     nonce=nonce)


class GuildContext(Context):
    guild: discord.Guild
    author: discord.Member


class Krazon(Bot[Context]):
    voice_states: Dict[int, VoiceState]
    context_cls = Context

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.voice_states = {}

        super().__init__(*args, **kwargs)

        if not discord.opus.is_loaded():
            discord.opus.load_opus(self.config.get('opus', 'path'))

        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.add_command(self.play)
        self.add_command(self.list)
        self.add_command(self.add)

    @property
    def storage_path(self) -> Path:
        return Path(self.config.get('storage', 'path'))

    def get_voice_state(self, ctx: GuildContext) -> VoiceState:
        state = self.voice_states.get(ctx.guild.id)

        if state is None:
            state = VoiceState(self)
            self.voice_states[ctx.guild.id] = state

        return state

    @commands.command()
    @commands.guild_only()
    async def play(self, ctx: GuildContext, name: str) -> None:
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await ctx.send_response('You must be connected to a voice channel to play a clip')

        channel = ctx.author.voice.channel

        if channel.user_limit == len(channel.members):
            await ctx.send_response('Cannot connect to voice channel to play the clip: too many members connected')
            return

        clip: Optional[Clip] = await ctx.select_one(name, str(ctx.author.id), table='clips',
                                                    where=['name = $1', 'member_id = $2'])

        if clip is None:
            await ctx.send_response(f'No clip found with name `{name}`')
            return

        client = await channel.connect()
        path = self.storage_path / str(ctx.author.id) / clip['filename']
        source = discord.FFmpegPCMAudio(str(path))
        client.play(source)

    @commands.command()
    async def list(self, ctx: Context) -> None:
        clips: List[Clip] = await ctx.select_all(str(ctx.author.id), table='clips',
                                                 where=['member_id = $1'])

        if len(clips) > 0:
            paginator = EmbedPaginator()

            for clip in clips:
                paginator.add_line(f'{clip["name"]}: {clip["filename"]}')

            for page in paginator:
                await ctx.send_response(page)
        else:
            await ctx.send_response('No clips found')

    @commands.command()
    async def add(self, ctx: Context, name: str) -> None:
        clip: Optional[Clip] = await ctx.select_one(name, str(ctx.author.id), table='clips',
                                                    where=['name = $1', 'member_id = $2'])

        if clip is not None:
            await ctx.send_response(f'A clip already exists with name `{name}`')
            return

        if len(ctx.message.attachments) == 0:
            await ctx.send_response('You must attach a sound file to the message')
            return

        author_path = self.storage_path / str(ctx.author.id)
        author_path.mkdir(parents=True, exist_ok=True)

        attachment = ctx.message.attachments[0]
        attachment_path = author_path / attachment.filename

        if attachment_path.exists():
            await ctx.send_response(f'A file named `{attachment.filename}` has already been uploaded. '
                                    'Rename the file and try again.')
            return

        await attachment.save(str(attachment_path.resolve()))
        await ctx.insert_into(table='clips',
                              values={
                                  'name': name,
                                  'member_id': str(ctx.author.id),
                                  'filename': attachment.filename
                              })

        await ctx.send_response(f'Successfully added `{name}`')

    @commands.command()
    async def remove(self, ctx: Context, name: str) -> None:
        clip: Optional[Clip] = await ctx.select_one(name, str(ctx.author.id), table='clips',
                                                    where=['name = $1', 'member_id = $2'])

        if clip is None:
            await ctx.send_response(f'No clip found with name `{name}`')
            return

        file_path = self.storage_path / str(ctx.author.id) / clip['filename']

        if file_path.exists():
            file_path.unlink()

        await ctx.delete_from(clip['id'], table='clips', where=['id = $1'])
        await ctx.send_response(f'Clip `{name}` removed')

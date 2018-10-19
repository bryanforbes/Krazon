from __future__ import annotations

from typing import Optional, Union, List
from datetime import datetime
from mypy_extensions import TypedDict

import discord

from botus_receptus import EmbedContext
from botus_receptus.context import FooterData, AuthorData, FieldData


class ClipRecord(TypedDict):
    id: int
    name: str
    member_id: str
    hash: str
    filename: str


class Context(EmbedContext):
    async def send_error(self, description: str, *,
                         title: Optional[str] = None,
                         footer: Optional[Union[str, FooterData]] = None,
                         thumbnail: Optional[str] = None,
                         author: Optional[Union[str, AuthorData]] = None,
                         image: Optional[str] = None,
                         timestamp: Optional[datetime] = None,
                         fields: Optional[List[FieldData]] = None,
                         tts: bool = False, file: Optional[discord.File] = None,
                         files: Optional[List[discord.File]] = None, delete_after: Optional[float] = 5,
                         nonce: Optional[int] = None) -> discord.Message:
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
                            tts: bool = False, file: Optional[discord.File] = None,
                            files: Optional[List[discord.File]] = None, delete_after: Optional[float] = None,
                            nonce: Optional[int] = None) -> discord.Message:
        return await self.send_embed(description, color=color, title=title, footer=footer,
                                     thumbnail=thumbnail, author=author, image=image, timestamp=timestamp,
                                     fields=fields, tts=tts, file=file, files=files, delete_after=delete_after,
                                     nonce=nonce)


class GuildContext(Context):
    guild: discord.Guild
    author: discord.Member

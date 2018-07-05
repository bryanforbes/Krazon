from discord.ext import commands


class ClipNotFound(commands.CommandError):
    def __init__(self, name: str) -> None:
        super().__init__(message=f'No clip named `{name}` found')


class FilenameExists(commands.CommandError):
    def __init__(self, filename: str) -> None:
        super().__init__(message=f'A file named `{filename}` has already been uploaded. '
                         'Rename the file and try again.')


class MustBeConnected(commands.CommandError):
    def __init__(self) -> None:
        super().__init__(message='You must be connected to a voice channel to play a clip')


class TooManyMembers(commands.CommandError):
    def __init__(self) -> None:
        super().__init__(message='Cannot connect to voice channel to play the clip: too many members connected')

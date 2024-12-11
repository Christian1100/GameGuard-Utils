import os
import string
import secrets
from pathlib import Path
from typing import Callable, Optional, List, TYPE_CHECKING
import asyncio
import discord
from discord import app_commands
from fortnite_api import GameLanguage
from redbot.core.i18n import get_locale

if TYPE_CHECKING:
    from redbot.core.bot import Red


def unpack_error(e: Exception) -> Exception:
    if hasattr(e, 'original'):
        return unpack_error(e.original)
    return e


def get_game_language() -> GameLanguage:
    code = get_locale()
    try:
        gl = GameLanguage(code)
    except ValueError:
        try:
            gl = GameLanguage(code[:2])
        except ValueError:
            gl = GameLanguage.ENGLISH
    return gl


def create_locale_str_factory(
    name: str, file_location: str | Path | os.PathLike
) -> Callable[[str], app_commands.locale_str]:
    def _locale_str(untranslated: str) -> app_commands.locale_str:
        return app_commands.locale_str(untranslated, name=name, file_location=file_location)

    return _locale_str


async def get_command_mention(bot: "Red", name: str) -> str:
    name = name.lower()
    name_split = name.split(' ')
    if not name_split:
        return f'`/{name}`'
    commands = await bot.list_enabled_app_commands()
    for command_name, command_id in commands['slash'].items():
        if command_name != name_split[0]:
            continue
        return f'</{name}:{command_id}>'
    return f'`/{name}`'


async def defer_interaction(interaction: discord.Interaction):
    await asyncio.sleep(
        2 - (discord.utils.utcnow() - interaction.created_at).total_seconds()
    )
    if not interaction.response.is_done():
        await interaction.response.defer()


async def send_respond(interaction: discord.Interaction, **kwargs):
    if not interaction.response.is_done():
        try:
            return await interaction.response.send_message(**kwargs)
        except discord.HTTPException as e:
            if e.code != 40060:
                raise e
    await interaction.followup.send(**kwargs)


async def edit_respond(interaction: discord.Interaction, **kwargs):
    if not interaction.response.is_done():
        try:
            return await interaction.response.edit_message(**kwargs)
        except discord.HTTPException as e:
            if e.code != 40060:
                raise e
    await interaction.edit_original_response(**kwargs)


def generate_random_string(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_file_format(
    files: List[discord.Attachment],
    filename: Optional[str] = None,
    extensions: Optional[List[str]] = None,
    max_files: Optional[int] = 1,
):
    filtered_files = []
    for file in files:
        name, ext = file.filename.rsplit(".", 1)
        name, ext = name.lower(), ext.lower()

        if (filename is None or name == filename.lower()) and (
            extensions is None or ext in [e.lower() for e in extensions]
        ):
            filtered_files.append(ext)

        if max_files is not None and len(filtered_files) >= max_files:
            break

    return filtered_files

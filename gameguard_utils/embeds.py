import discord
from typing import Optional


def get_error_embed(
    title: Optional[str] = None,
    description: Optional[str] = None,
    error: Optional[str] = None,
) -> discord.Embed:
    if error:
        description += f"\n```{error}```"

    embed = discord.Embed(
        title=title,
        description=description,
        colour=discord.Colour.dark_red(),
    )
    return embed

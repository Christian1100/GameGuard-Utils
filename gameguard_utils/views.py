from typing import List, Any, Optional, TYPE_CHECKING
from contextlib import suppress
import discord

if TYPE_CHECKING:
    from redbot.core.bot import Red


class View(discord.ui.View):
    def __init__(
        self,
        interaction: Optional[discord.Interaction] = None,
        *,
        owner: Optional[discord.abc.User] = None,
        owner_only: bool = True,
        message: Optional[discord.Message] = None,
        timeout: Optional[float] = 300.0,
    ):
        super().__init__(timeout=timeout)
        self._enabled: bool = interaction is not None
        self.interaction: Optional[discord.Interaction] = interaction
        self.owner: Optional[discord.User] = owner or (interaction.user if interaction else None)
        self.owner_only: bool = owner_only
        self.interaction_message: Optional[discord.Message] = message

    async def on_timeout(self) -> None:
        for item in self.children:
            if item.is_dispatchable():
                self.remove_item(item)

        with suppress(Exception):
            if self._enabled:
                await self.interaction.edit_original_response(view=self)
            elif self.interaction_message:
                await self.interaction_message.edit(view=self)

    async def interaction_check(self, interaction: discord.Interaction["Red"], /) -> bool:
        if self.owner_only and self.owner and interaction.user != self.owner:
            embed = discord.Embed(colour=discord.Colour.dark_red())
            embed.description = 'You are not authorized to interact with this menu.'
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    async def on_error(
        self,
        interaction: discord.Interaction["Red"],
        error: Exception,
        item: discord.ui.Item[Any],
        /,
    ) -> None:
        interaction.client.dispatch('error', 'on_view_interaction', self, item, interaction, error=error)

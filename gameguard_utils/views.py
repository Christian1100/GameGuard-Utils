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
        disable_only: Optional[bool] = True,
        message: Optional[discord.Message] = None,
        timeout: Optional[float] = 300.0,
    ):
        super().__init__(timeout=timeout)
        self._enabled: bool = interaction is not None
        self.interaction: Optional[discord.Interaction] = interaction
        self.owner: Optional[discord.User] = owner or (interaction.user if interaction else None)
        self.owner_only: bool = owner_only
        self.disable_only: Optional[bool] = True
        self.interaction_message: Optional[discord.Message] = message

    async def on_timeout(self) -> None:
        if self.disable_only:
            new_children = []
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.url:
                    disabled_button = discord.ui.Button(
                        label=item.label,
                        style=discord.ButtonStyle.grey,
                        disabled=True,
                        row=item.row
                    )
                    new_children.append(disabled_button)
                else:
                    if item.is_dispatchable():
                        item.disabled = True
                    new_children.append(item)
            
            self.clear_items()
            for new_item in new_children:
                self.add_item(new_item)
        else:
            for item in self.children:
                if item.is_dispatchable():
                    self.remove_item(item)

        with suppress(Exception):
            if self._enabled:
                if self.interaction.response.is_done():
                    await self.interaction.edit_original_response(view=self)
                else:
                    await self.interaction.response.edit_message(view=self)
            elif self.interaction_message:
                await self.interaction_message.edit(view=self)

    async def interaction_check(self, interaction: discord.Interaction["Red"], /) -> bool:
        if self.owner_only and self.owner and interaction.user != self.owner:
            embed = discord.Embed(colour=discord.Colour.dark_red())
            embed.description = 'You are not authorized to interact with this menu.'
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

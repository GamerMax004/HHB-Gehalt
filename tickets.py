import discord
from discord.ext import commands
from datetime import datetime, timezone
import time


async def panel_embed_senden(bot, kanal: discord.TextChannel, config: dict):
    """Sendet das Dokumentations-Panel in den Panel-Kanal."""
    guild = kanal.guild
    e = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
    if guild and guild.icon:
        e.set_author(name=guild.name, icon_url=guild.icon.url)
        e.set_thumbnail(url=guild.icon.url)
    e.title       = "Dokumentation"
    e.description = (
        "Klicke den Button unten um eine neue Dokumentation einzureichen. Du wirst gebeten, ein kurzes Formular auszufüllen:\n"
        "**• Name des Tickets**\n"
        "**• Worum ging es?**\n"
        "**• Gab es Probleme?**"
    )
    msg = await kanal.send(embed=e, view=PanelView(bot))
    config["panel_nachricht_id"] = str(msg.id)
    bot.save_json(bot.CONFIG_FILE, config)
    return msg


class PanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Dokumentieren!", style=discord.ButtonStyle.primary, emoji="<:8879edit:1477410636018221128>", custom_id="ticket_erstellen")
    async def ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal(self.bot))


class TicketModal(discord.ui.Modal, title="Neue Dokumentation"):
    ticket_name = discord.ui.TextInput(
        label="Name des Tickets",
        placeholder="[Kategorie]-[User]",
        required=True, max_length=100
    )
    worum = discord.ui.TextInput(
        label="Worum ging es?",
        style=discord.TextStyle.paragraph,
        placeholder="Beschreibe worum es im Ticket ging.",
        required=True, max_length=1000
    )
    probleme = discord.ui.TextInput(
        label="Gab es Probleme?",
        style=discord.TextStyle.paragraph,
        placeholder="Falls ja, beschreibe die Probleme so genau wie möglich. Falls nein: 'Keine'.",
        required=True, max_length=1000
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        config   = self.bot.load_json(self.bot.CONFIG_FILE)
        kanal_id = config.get("kanaele", {}).get("dokumentationen")
        if not kanal_id:
            return await interaction.response.send_message(
                "Fehler: `Dokumentationskanal` nicht konfiguriert! Bitte einen Administrator kontaktieren.", ephemeral=True
            )
        kanal = interaction.guild.get_channel(int(kanal_id))
        if not kanal:
            return await interaction.response.send_message("Fehler: `Dokumentationskanal` nicht gefunden!", ephemeral=True)

        jetzt     = datetime.now(timezone.utc)
        ticket_id = int(time.time())
        guild     = interaction.guild

        e = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
        if guild and guild.icon:
            e.set_author(name=guild.name, icon_url=guild.icon.url)
        e.title = "Dokumentation"
        e.add_field(name="__Mitarbeiter__", value=f"> <:7549member:1477410605240549637> - {interaction.user.mention}", inline=True)
        e.add_field(name="__Datum__", value=f"<t:{int(jetzt.timestamp())}:F>", inline=True)
        e.add_field(name="__Name des Tickets__", value=f"> <:4748ticket:1477410582691840140> - `{self.ticket_name.value}`", inline=False)
        e.add_field(name="__Worum ging es?__", value=f"```{self.worum.value}```", inline=False)
        e.add_field(name="__Gab es Probleme?__", value=f"```{self.probleme.value}```", inline=False)
        e.set_thumbnail(url=interaction.user.display_avatar.url)
        await kanal.send(embed=e)

        # Ticket gutschreiben
        nd      = self.bot.load_json(self.bot.USERS_FILE)
        uid     = str(interaction.user.id)
        if uid not in nd:
            nd[uid] = {"gesamt_shift_sekunden": 0, "shift_anzahl": 0, "tickets": 0, "urlaubstage": 0, "benutzername": ""}
        nd[uid]["tickets"]      = nd[uid].get("tickets", 0) + 1
        nd[uid]["benutzername"] = interaction.user.display_name
        self.bot.save_json(self.bot.USERS_FILE, nd)

        # Bestätigung
        best = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
        if guild and guild.icon:
            best.set_author(name=guild.name, icon_url=guild.icon.url)
        best.title       = "Dokumenation eingereicht!"
        best.description = f"Deine Dokumentation **{self.ticket_name.value}** wurde erfolgreich gespeichert."
        best.add_field(name="__Bearbeitete Tickets__", value=f"> <:4748ticket:1477410582691840140> - `{str(nd[uid].get("tickets", 1))}`", inline=True)
        await interaction.response.send_message(embed=best, ephemeral=True)


class TicketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(PanelView(bot))

    @commands.Cog.listener()
    async def on_ready(self):
        print("[Tickets] Panel-View registriert.")


async def setup(bot):
    await bot.add_cog(TicketsCog(bot))

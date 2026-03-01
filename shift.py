import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import time

# ============================================================
# HILFSFUNKTIONEN
# ============================================================
def dauer_formatieren(sekunden: float) -> str:
    sekunden = int(max(0, sekunden))
    h = sekunden // 3600
    m = (sekunden % 3600) // 60
    s = sekunden % 60
    teile = []
    if h > 0: teile.append(f"{h} {'Stunde' if h == 1 else 'Stunden'}")
    if m > 0: teile.append(f"{m} {'Minute' if m == 1 else 'Minuten'}")
    if s > 0 or not teile: teile.append(f"{s} {'Sekunde' if s == 1 else 'Sekunden'}")
    return ", ".join(teile)

def dauer_relativ(sekunden: float) -> str:
    sekunden = int(max(0, sekunden))
    jahre  = sekunden // (365 * 86400); sekunden %= (365 * 86400)
    monate = sekunden // (30  * 86400); sekunden %= (30  * 86400)
    wochen = sekunden // (7   * 86400); sekunden %= (7   * 86400)
    tage   = sekunden // 86400;         sekunden %= 86400
    stunden = sekunden // 3600;         sekunden %= 3600
    minuten = sekunden // 60
    teile = []
    if jahre:   teile.append(f"{jahre} {'Jahr' if jahre == 1 else 'Jahre'}")
    if monate:  teile.append(f"{monate} {'Monat' if monate == 1 else 'Monate'}")
    if wochen:  teile.append(f"{wochen} {'Woche' if wochen == 1 else 'Wochen'}")
    if tage:    teile.append(f"{tage} {'Tag' if tage == 1 else 'Tage'}")
    if not teile:
        if stunden: teile.append(f"{stunden} {'Stunde' if stunden == 1 else 'Stunden'}")
        if minuten: teile.append(f"{minuten} {'Minute' if minuten == 1 else 'Minuten'}")
    return ", ".join(teile) if teile else "weniger als eine Minute"

def dauer_zu_sekunden(dauer: str) -> int:
    d = dauer.lower().strip()
    try:
        if d.endswith("d"): return int(d[:-1]) * 86400
        if d.endswith("w"): return int(d[:-1]) * 7 * 86400
        if d.endswith("m"): return int(d[:-1]) * 30 * 86400
    except ValueError:
        pass
    return 86400

def dauer_zu_tage(dauer: str) -> int:
    return dauer_zu_sekunden(dauer) // 86400

def aktuelle_shift_sekunden(shift: dict) -> float:
    if shift.get("status") == "aktiv" and shift.get("start_zeit"):
        return (
            shift.get("gespeicherte_sekunden", 0)
            + (time.time() - shift["start_zeit"])
            - shift.get("gesamt_pause_sekunden", 0)
        )
    return shift.get("gespeicherte_sekunden", 0)

def nd_laden(bot, uid: str) -> dict:
    alle = bot.load_json(bot.USERS_FILE)
    if uid not in alle:
        alle[uid] = {
            "gesamt_shift_sekunden": 0,
            "shift_anzahl":          0,
            "tickets":               0,
            "urlaubstage":           0,
            "benutzername":          "",
        }
    return alle

def nd_speichern(bot, alle: dict):
    bot.save_json(bot.USERS_FILE, alle)

def shifts_laden(bot) -> dict:
    return bot.load_json(bot.SHIFTS_FILE)

def shifts_speichern(bot, daten: dict):
    bot.save_json(bot.SHIFTS_FILE, daten)

def shift_typ(bot, member: discord.Member) -> str:
    config          = bot.load_json(bot.CONFIG_FILE)
    leitungs_ids    = config.get("rollen", {}).get("leitungsebene", [])
    mitarbeiter_ids = config.get("rollen", {}).get("mitarbeiter",   [])
    rollen = list(member.roles)
    for r in rollen:
        if str(r.id) in leitungs_ids:
            return r.name
    for r in reversed(rollen):
        if str(r.id) in mitarbeiter_ids:
            return r.name
    return "Mitarbeiter"

def durchschnitt(nd_user: dict) -> float:
    anzahl = nd_user.get("shift_anzahl", 0)
    gesamt = nd_user.get("gesamt_shift_sekunden", 0)
    return gesamt / anzahl if anzahl > 0 else 0.0


# ============================================================
# DM BENACHRICHTIGUNGEN (nach Screenshot-Design)
# Gelbe Leiste = Pending, Grüne = Approved, Rote = Ended/Rejected
# ============================================================
async def dm_urlaub_ausstehend(guild: discord.Guild, member: discord.Member, dauer: str, end_ts: int, antrag_id: str):
    """Bild: gelbe Leiste — 'Urlaubsantrag ausstehend'"""
    try:
        e = discord.Embed(color=discord.Color.from_rgb(255, 204, 0))  # Gelb
        if guild and guild.icon:
            e.set_author(name=guild.name, icon_url=guild.icon.url)
        e.title = "Urlaubsantrag ausstehend!"
        e.description = (
            f"> Dein Urlaubsantrag wurde an die Leitungsebene zur Genehmigung weitergeleitet. Bei Genehmigung endet dein Urlaub am <t:{end_ts}:F>.\n"
            f"> Zum Einsehen nutze </leave manage:1477325994473033742>. Solltest du Fragen haben oder deinen Urlaub bearbeiten möchtest, wende dich an die Leitungsebene."
        )
        e.set_thumbnail(url="https://cdn.discordapp.com/emojis/1477446734530740325.webp?size=40&quality=lossless&animated=true")
        await member.send(embed=e)
    except discord.Forbidden:
        pass

async def dm_urlaub_genehmigt(guild: discord.Guild, member: discord.Member, dauer: str, end_ts: int):
    """Bild: grüne Leiste — 'Urlaub genehmigt'"""
    try:
        e = discord.Embed(color=discord.Color.green())
        if guild and guild.icon:
            e.set_author(name=guild.name, icon_url=guild.icon.url)
        e.title = "Urlaub genehmigt!"
        e.description = (
            f"> Um deinen Urlaub einzusehen, nutze </leave manage:1477325994473033742>.Solltest du Fragen haben oder deinen Urlaub bearbeiten möchtest, wende dich an die Leitungsebene.\n\n"
            f"> Dein Urlaub endet am <t:{end_ts}:F>."
        )
        e.set_thumbnail(url="https://cdn.discordapp.com/emojis/1477446732353638471.webp?size=40&quality=lossless&animated=true")
        await member.send(embed=e)
    except discord.Forbidden:
        pass

async def dm_urlaub_abgelehnt(guild: discord.Guild, member: discord.Member, dauer: str):
    """Rote Leiste — 'Urlaubsantrag abgelehnt'"""
    try:
        e = discord.Embed(color=discord.Color.red())
        if guild and guild.icon:
            e.set_author(name=guild.name, icon_url=guild.icon.url)
        e.title = "Urlaubsantrag abgelehnt!"
        e.description = (
            "> Dein Urlaubsantrag wurde leider abgelehnt.\n"
            "> Bei Fragen wende dich an die Leitungsebene."
        )
        e.set_thumbnail(url="https://cdn.discordapp.com/emojis/1477446735671333121.webp?size=40&quality=lossless&animated=true")
        await member.send(embed=e)
    except discord.Forbidden:
        pass

async def dm_urlaub_beendet(guild: discord.Guild, member: discord.Member, start_ts: int):
    """Bild: rote Leiste — 'Urlaub beendet'"""
    try:
        e = discord.Embed(color=discord.Color.red())
        if guild and guild.icon:
            e.set_author(name=guild.name, icon_url=guild.icon.url)
        e.title = "Urlaub beendet!"
        e.description = (
            f"> Dein Urlaub, der am <t:{start_ts}:F> (vor {dauer_relativ(int(time.time()) - start_ts)}) begann, ist beendet. Um einen neuen zu beantragen, nutze </leave manage:1477325994473033742>."
        )
        e.set_thumbnail(url="https://cdn.discordapp.com/emojis/1477446735671333121.webp?size=40&quality=lossless&animated=true")
        await member.send(embed=e)
    except discord.Forbidden:
        pass


# ============================================================
# SHIFT MANAGE VIEW — dynamische Buttons je nach Status
#
# Kein aktiver Shift  → nur Start (Pause/End ausgegraut)
# Aktiver Shift       → nur Pause + End (Start ausgegraut)
# Pausierter Shift    → nur Start (Pause/End ausgegraut)
# Beendeter Shift     → alle Buttons deaktiviert
# ============================================================
def shift_embed_erstellen(bot, member: discord.Member, status: str) -> discord.Embed:
    uid     = str(member.id)
    alle    = nd_laden(bot, uid)
    nd_user = alle[uid]
    aktiver = shifts_laden(bot).get(uid)

    anzeige = nd_user["gesamt_shift_sekunden"]
    if aktiver and status in ("aktiv", "pausiert"):
        anzeige += aktuelle_shift_sekunden(aktiver)

    # Farben für die verschiedenen Status
    colors = {
        "aktiv": 0x43b581,
        "pausiert": 0xfba71c,
        "beendet": 0xef4747,
        "inaktiv": 0x2c2f33
    }
    color = colors.get(status, 0x2c2f33)

    e = discord.Embed(color=color)
    e.set_author(name="Shift Management", icon_url=member.display_avatar.url)

    # Status-Zeile
    status_bild = {
        "inaktiv":  "https://cdn.discordapp.com/emojis/1477463382440415384.webp?size=128&quality=lossless&animated=true",
        "aktiv":    "https://cdn.discordapp.com/emojis/1477446732353638471.webp?size=64&quality=lossless&animated=true",
        "pausiert": "https://cdn.discordapp.com/emojis/1477446734530740325.webp?size=64&quality=lossless&animated=true",
        "beendet":  "https://cdn.discordapp.com/emojis/1477446735671333121.webp?size=64&quality=lossless&animated=true",
    }.get(status, "https://cdn.discordapp.com/emojis/1477463382440415384.webp?size=64&quality=lossless&animated=true")

    e.add_field(
        name="__Shift Informationen__",
        value=(
            f"> **Anzahl:** `{nd_user['shift_anzahl']}`\n"
            f"> **Gesamtdauer:** {dauer_formatieren(anzeige)}\n"
            f"> **Durchschnitt:** {dauer_formatieren(durchschnitt(nd_user))}"
        ),
        inline=False
    )
    e.set_thumbnail(url=f"{status_bild}")

    # Aktive Schicht: laufende Zeit anzeigen
    if aktiver and status == "aktiv":
        effektiver_start = int(time.time() - aktuelle_shift_sekunden(aktiver))
        e.add_field(name="__Shift gestartet:__", value=f"<t:{effektiver_start}:R>", inline=False)
    elif aktiver and status == "pausiert":
        laufend = aktuelle_shift_sekunden(aktiver)
        e.add_field(name="__Shift pausiert:__", value=f"<t:{int(time.time() - laufend)}:R>", inline=False)

    return e


class ShiftView(discord.ui.View):
    """
    Buttons werden je nach Shift-Status dynamisch aktiviert/deaktiviert:
    - inaktiv  → Start ✅ | Pause ❌ | End ❌
    - aktiv    → Start ❌ | Pause ✅ | End ✅
    - pausiert → Start ✅ | Pause ❌ | End ❌
    - beendet  → Start ❌ | Pause ❌ | End ❌
    """
    def __init__(self, besitzer_id: int, bot, status: str = "inaktiv"):
        super().__init__(timeout=None)
        self.besitzer_id = besitzer_id
        self.bot         = bot
        self._buttons_setzen(status)

    def _buttons_setzen(self, status: str):
        """Setzt Aktivierung der Buttons je nach Status."""
        self.clear_items()

        start_aktiv  = status in ("inaktiv", "pausiert")
        pause_aktiv  = status == "aktiv"
        end_aktiv    = status == "aktiv"
        alle_aus     = status == "beendet"

        # Start-Button
        start_btn = discord.ui.Button(
            label="Start",
            style=discord.ButtonStyle.success,
            emoji="🕐",
            custom_id="sv_start",
            disabled=not start_aktiv or alle_aus,
            row=0
        )
        start_btn.callback = self.btn_start
        self.add_item(start_btn)

        # Pause-Button
        pause_btn = discord.ui.Button(
            label="Pause",
            style=discord.ButtonStyle.primary,
            emoji="🕐",
            custom_id="sv_pause",
            disabled=not pause_aktiv or alle_aus,
            row=0
        )
        pause_btn.callback = self.btn_pause
        self.add_item(pause_btn)

        # End-Button
        end_btn = discord.ui.Button(
            label="End",
            style=discord.ButtonStyle.danger,
            emoji="🕐",
            custom_id="sv_end",
            disabled=not end_aktiv or alle_aus,
            row=0
        )
        end_btn.callback = self.btn_end
        self.add_item(end_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.besitzer_id:
            await interaction.response.send_message("Fehler: `Buttons` sind für dich deaktiviert!", ephemeral=True)
            return False
        return True

    async def btn_start(self, interaction: discord.Interaction):
        uid   = str(interaction.user.id)
        alle  = shifts_laden(self.bot)
        s     = alle.get(uid, {})
        jetzt = time.time()

        if s.get("status") == "pausiert":
            # Pause fortsetzen
            s["gesamt_pause_sekunden"] = s.get("gesamt_pause_sekunden", 0) + (jetzt - s.get("pause_start", jetzt))
            s["pause_start"] = None
            s["status"] = "aktiv"
        else:
            # Neue Schicht starten
            s = {
                "status":                "aktiv",
                "start_zeit":            jetzt,
                "pause_start":           None,
                "gesamt_pause_sekunden": 0,
                "gespeicherte_sekunden": 0,
                "benutzername":          interaction.user.display_name,
            }

        alle[uid] = s
        shifts_speichern(self.bot, alle)
        nd = nd_laden(self.bot, uid)
        nd[uid]["benutzername"] = interaction.user.display_name
        nd_speichern(self.bot, nd)

        self._buttons_setzen("aktiv")
        await interaction.response.edit_message(
            embed=shift_embed_erstellen(self.bot, interaction.user, "aktiv"),
            view=self
        )

    async def btn_pause(self, interaction: discord.Interaction):
        uid  = str(interaction.user.id)
        alle = shifts_laden(self.bot)
        s    = alle.get(uid)
        if not s or s.get("status") != "aktiv":
            return await interaction.response.send_message("Fehler: `Shift` nicht aktiv!", ephemeral=True)

        s["status"]      = "pausiert"
        s["pause_start"] = time.time()
        alle[uid] = s
        shifts_speichern(self.bot, alle)

        self._buttons_setzen("pausiert")
        await interaction.response.edit_message(
            embed=shift_embed_erstellen(self.bot, interaction.user, "pausiert"),
            view=self
        )

    async def btn_end(self, interaction: discord.Interaction):
        uid  = str(interaction.user.id)
        alle = shifts_laden(self.bot)
        s    = alle.get(uid)
        if not s:
            return await interaction.response.send_message("Fehler: `Shift` nicht aktiv!", ephemeral=True)

        jetzt = time.time()
        pause = s.get("gesamt_pause_sekunden", 0)
        if s.get("status") == "pausiert":
            pause += jetzt - s.get("pause_start", jetzt)
        gesamt = max(0, s.get("gespeicherte_sekunden", 0) + (jetzt - s.get("start_zeit", jetzt)) - pause)

        nd = nd_laden(self.bot, uid)
        nd[uid]["gesamt_shift_sekunden"] += gesamt
        nd[uid]["shift_anzahl"]          += 1
        nd[uid]["benutzername"]           = interaction.user.display_name
        nd_speichern(self.bot, nd)
        alle.pop(uid, None)
        shifts_speichern(self.bot, alle)

        # Embed mit Abschluss-Info
        e = shift_embed_erstellen(self.bot, interaction.user, "beendet")
        e.add_field(name="__Shift beendet:__", value=f"> {dauer_formatieren(gesamt)}", inline=False)

        self._buttons_setzen("beendet")
        await interaction.response.edit_message(embed=e, view=self)


# ============================================================
# SHIFT ADMIN VIEW
# ============================================================
class ShiftAdminView(discord.ui.View):
    def __init__(self, ziel: discord.Member, bot):
        super().__init__(timeout=None)
        self.ziel = ziel
        self.bot  = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.bot.ist_leitungsebene(interaction.user):
            await interaction.response.send_message("Fehler: `Leitungsebene` benötigt!", ephemeral=True)
            return False
        return True

    def embed(self) -> discord.Embed:
        uid     = str(self.ziel.id)
        alle    = nd_laden(self.bot, uid)
        nd_user = alle[uid]
        aktiver = shifts_laden(self.bot).get(uid)
        anzeige = nd_user["gesamt_shift_sekunden"] + (aktuelle_shift_sekunden(aktiver) if aktiver else 0)

        e = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
        e.set_author(name="Shift Management", icon_url=self.ziel.display_avatar.url)
        e.add_field(
            name="__Shift Informationen__",
            value=(
                f"> **User:** {self.ziel.mention}\n"
                f"> **Anzahl:** `{nd_user['shift_anzahl']}`\n"
                f"> **Gesamtdauer:** {dauer_formatieren(anzeige)}\n"
                f"> **Durchschnitt:** {dauer_formatieren(durchschnitt(nd_user))}"
            ),
            inline=False
        )
        return e

    @discord.ui.select(
        placeholder="Shift Actions",
        options=[
            discord.SelectOption(label="Shiftliste anzeigen",      value="liste",     description="Übersicht aller Shiftdaten",          emoji="<:6523information:1477410598722470039>"),
            discord.SelectOption(label="Shift bearbeiten",         value="bearbeiten",description="Zeit hinzufügen, abziehen oder setzen", emoji="<:8879edit:1477410636018221128>"),
            discord.SelectOption(label="Aktive Shift löschen",     value="loeschen",  description="Laufende Shift löschen",             emoji="<:9426raidreport:1477410640787148913>"),
            discord.SelectOption(label="Alle Shiftdaten löschen",  value="leeren",    description="Alle Daten zurücksetzen",                emoji="<:9426raidreport:1477410640787148913>"),
        ],
        row=0
    )
    async def dropdown(self, interaction: discord.Interaction, select: discord.ui.Select):
        aktion = select.values[0]
        uid    = str(self.ziel.id)

        if aktion == "liste":
            alle    = nd_laden(self.bot, uid)
            nd_user = alle[uid]
            e = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
            e.set_author(name="__Shiftliste", icon_url=self.ziel.display_avatar.url)
            e.add_field(name="__Schichtanzahl__", value=
                            f"> **User:** {self.ziel.mention}\n"
                            f"> **Anzahl:** `{nd_user['shift_anzahl']}`\n"
                            f"> **Gesamtdauer:** {dauer_formatieren(anzeige)}\n"
                            f"> **Durchschnitt:** {dauer_formatieren(durchschnitt(nd_user))}",
                        inline=False)
            
            aktiver = shifts_laden(self.bot).get(uid)
            if aktiver:
                e.add_field(name="__Aktuelle Shift__", value=f"> {dauer_formatieren(aktuelle_shift_sekunden(aktiver))}", inline=True)
            return await interaction.response.send_message(embed=e, ephemeral=True)

        if aktion == "bearbeiten":
            return await interaction.response.send_modal(ShiftBearbeitenModal(self.ziel, self.bot))

        if aktion == "loeschen":
            alle = shifts_laden(self.bot)
            alle.pop(uid, None)
            shifts_speichern(self.bot, alle)
            await interaction.response.send_message(f"Aktive Shift von {self.ziel.mention} gelöscht!", ephemeral=True)
            await interaction.message.edit(embed=self.embed())
            return

        if aktion == "leeren":
            alle = shifts_laden(self.bot)
            alle.pop(uid, None)
            shifts_speichern(self.bot, alle)
            nd = nd_laden(self.bot, uid)
            nd[uid]["gesamt_shift_sekunden"] = 0
            nd[uid]["shift_anzahl"]          = 0
            nd_speichern(self.bot, nd)
            await interaction.response.send_message(f"Alle Shiftdaten von {self.ziel.mention} zurückgesetzt!", ephemeral=True)
            await interaction.message.edit(embed=self.embed())

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, emoji="🕐", row=1)
    async def admin_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid  = str(self.ziel.id)
        alle = shifts_laden(self.bot)
        if alle.get(uid, {}).get("status") == "aktiv":
            return await interaction.response.send_message("Fehler: `Shift` aktiv!", ephemeral=True)
        alle[uid] = {"status": "aktiv", "start_zeit": time.time(), "pause_start": None,
                     "gesamt_pause_sekunden": 0, "gespeicherte_sekunden": 0,
                     "benutzername": self.ziel.display_name}
        shifts_speichern(self.bot, alle)
        await interaction.response.send_message(f"Shift für {self.ziel.mention} gestartet!", ephemeral=True)
        await interaction.message.edit(embed=self.embed())

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.primary, emoji="🕐", row=1)
    async def admin_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid  = str(self.ziel.id)
        alle = shifts_laden(self.bot)
        s    = alle.get(uid)
        if not s or s.get("status") != "aktiv":
            return await interaction.response.send_message("Fehler: `Shift` nicht aktiv!", ephemeral=True)
        s["status"] = "pausiert"
        s["pause_start"] = time.time()
        alle[uid] = s
        shifts_speichern(self.bot, alle)
        await interaction.response.send_message("Shift pausiert!", ephemeral=True)
        await interaction.message.edit(embed=self.embed())

    @discord.ui.button(label="End", style=discord.ButtonStyle.danger, emoji="🕐", row=1)
    async def admin_end(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid  = str(self.ziel.id)
        alle = shifts_laden(self.bot)
        s    = alle.get(uid)
        if not s:
            return await interaction.response.send_message("Fehler: `Shift` nicht aktiv!", ephemeral=True)
        jetzt = time.time()
        pause = s.get("gesamt_pause_sekunden", 0)
        if s.get("status") == "pausiert":
            pause += jetzt - s.get("pause_start", jetzt)
        gesamt = max(0, s.get("gespeicherte_sekunden", 0) + (jetzt - s.get("start_zeit", jetzt)) - pause)
        nd = nd_laden(self.bot, uid)
        nd[uid]["gesamt_shift_sekunden"] += gesamt
        nd[uid]["shift_anzahl"]          += 1
        nd_speichern(self.bot, nd)
        alle.pop(uid, None)
        shifts_speichern(self.bot, alle)
        await interaction.response.send_message(f"Shift beendet (+{dauer_formatieren(gesamt)})!", ephemeral=True)
        await interaction.message.edit(embed=self.embed())


class ShiftBearbeitenModal(discord.ui.Modal, title="Schicht bearbeiten"):
    wert = discord.ui.TextInput(
        label="Zeit anpassen",
        placeholder="+2 hinzufügen  |  -1 abziehen  |  =5 genau setzen  (in Stunden)",
        required=True, max_length=10
    )
    def __init__(self, ziel: discord.Member, bot):
        super().__init__()
        self.ziel = ziel
        self.bot  = bot

    async def on_submit(self, interaction: discord.Interaction):
        uid = str(self.ziel.id)
        roh = self.wert.value.strip().replace(",", ".")
        try:
            if roh.startswith("="):
                neue_sek = max(0, int(float(roh[1:]) * 3600))
                nd = nd_laden(self.bot, uid)
                nd[uid]["gesamt_shift_sekunden"] = neue_sek
                nd_speichern(self.bot, nd)
                return await interaction.response.send_message(
                    f"Shift auf **{dauer_formatieren(neue_sek)}** gesetzt!", ephemeral=True)
            delta = int(float(roh) * 3600)
        except ValueError:
            return await interaction.response.send_message("Fehler: `Wert` ungültig!", ephemeral=True)
        nd = nd_laden(self.bot, uid)
        nd[uid]["gesamt_shift_sekunden"] = max(0, nd[uid]["gesamt_shift_sekunden"] + delta)
        nd_speichern(self.bot, nd)
        aktion = "hinzugefügt" if delta >= 0 else "abgezogen"
        await interaction.response.send_message(
            f"**{dauer_formatieren(abs(delta))}** {aktion}. "
            f"Neu: **{dauer_formatieren(nd[uid]['gesamt_shift_sekunden'])}**", ephemeral=True)


# ============================================================
# URLAUBS VIEWS
# ============================================================
class UrlaubsView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, emoji="🕐", custom_id="uv_start")
    async def urlaub_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(UrlaubsAntragModal(self.bot))

    @discord.ui.button(label="Erweiterte Historie", style=discord.ButtonStyle.secondary, custom_id="uv_history")
    async def urlaub_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid       = str(interaction.user.id)
        db        = self.bot.load_json(self.bot.LEAVE_FILE)
        eintraege = db.get(uid, {}).get("eintraege", [])
        e = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
        e.set_author(name=f"@{interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        e.title = "Urlaubsverwaltung"
        if eintraege:
            zeilen = []
            for i, entry in enumerate(eintraege, 1):
                ts     = entry.get("zeitstempel", time.time())
                dt     = datetime.fromtimestamp(ts, tz=timezone.utc)
                status = entry.get("status", "ausstehend")
                icon   = "✅" if status == "genehmigt" else "❌" if status == "abgelehnt" else "⏳"
                zeilen.append(f"{i}. {dt.strftime('%d. %B %Y um %H:%M')} [{entry.get('dauer','?')}] {icon}")
            e.add_field(name="Alle Einträge", value="\n".join(zeilen), inline=False)
        else:
            e.add_field(name="Alle Einträge", value="Keine Urlaubseinträge.", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)


class UrlaubsAntragModal(discord.ui.Modal, title="Urlaubsantrag stellen"):
    begruendung = discord.ui.TextInput(
        label="Begründung", style=discord.TextStyle.paragraph,
        placeholder="Warum möchtest du Urlaub nehmen?", required=True, max_length=500
    )
    dauer_feld = discord.ui.TextInput(
        label="Dauer", placeholder="1d (1 Tag)  |  2w (2 Wochen)  |  1m (1 Monat)",
        required=True, max_length=10
    )
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        config   = self.bot.load_json(self.bot.CONFIG_FILE)
        kanal_id = config.get("kanaele", {}).get("urlaubsantraege")
        if not kanal_id:
            return await interaction.response.send_message("Fehler: `Kanel` nicht konfiguriert!", ephemeral=True)
        kanal = interaction.guild.get_channel(int(kanal_id))
        if not kanal:
            return await interaction.response.send_message("Fehler: `Kanel` nicht gefunden!", ephemeral=True)

        jetzt      = datetime.now(timezone.utc)
        dur_sek    = dauer_zu_sekunden(self.dauer_feld.value)
        end_ts     = int(jetzt.timestamp()) + dur_sek
        antrag_id  = str(int(jetzt.timestamp()))

        # Kanal-Embed (für Leitungsebene)
        e = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
        e.set_author(name=f"Urlaubsantrag: @{interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        e.add_field(name="Antragsteller", value=interaction.user.mention,    inline=True)
        e.add_field(name="Dauer",         value=self.dauer_feld.value,        inline=True)
        e.add_field(name="Endet am",      value=f"<t:{end_ts}:F>",            inline=False)
        e.add_field(name="Begründung",    value=self.begruendung.value,       inline=False)
        e.set_footer(text=f"Antrags-ID: {antrag_id}  •  User ID: {interaction.user.id}")

        await kanal.send(
            embed=e,
            view=GenehmigungsView(interaction.user.id, self.dauer_feld.value, dur_sek, antrag_id, self.bot)
        )

        # DM: ausstehend
        await dm_urlaub_ausstehend(interaction.guild, interaction.user, self.dauer_feld.value, end_ts, antrag_id)
        await interaction.response.send_message(
            "Dein Urlaubsantrag wurde abgeschickt! Du erhältst eine DM sobald er bearbeitet wurde.",
            ephemeral=True
        )


class GenehmigungsView(discord.ui.View):
    def __init__(self, uid: int, dauer: str, dur_sek: int, antrag_id: str, bot):
        super().__init__(timeout=None)
        self.uid       = uid
        self.dauer     = dauer
        self.dur_sek   = dur_sek
        self.antrag_id = antrag_id
        self.bot       = bot

    @discord.ui.button(label="<:3518checkmark:1477410569941159959> Genehmigen", style=discord.ButtonStyle.success)
    async def genehmigen(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.bot.ist_leitungsebene(interaction.user):
            return await interaction.response.send_message("Fehler: `Leitungsebene` benötigt!", ephemeral=True)
        uid_str    = str(self.uid)
        jetzt      = time.time()
        end_ts     = int(jetzt + self.dur_sek)
        start_ts   = int(jetzt)

        db = self.bot.load_json(self.bot.LEAVE_FILE)
        if uid_str not in db: db[uid_str] = {"eintraege": [], "aktiv": []}
        db[uid_str]["eintraege"].append({
            "dauer": self.dauer, "zeitstempel": jetzt, "start_zeitstempel": start_ts,
            "end_zeitstempel": end_ts, "status": "genehmigt", "antrag_id": self.antrag_id
        })
        db[uid_str]["aktiv"].append({
            "dauer": self.dauer, "start_zeitstempel": start_ts,
            "end_zeitstempel": end_ts, "benutzername": ""
        })
        self.bot.save_json(self.bot.LEAVE_FILE, db)

        nd = nd_laden(self.bot, uid_str)
        nd[uid_str]["urlaubstage"] = nd[uid_str].get("urlaubstage", 0) + dauer_zu_tage(self.dauer)
        nd_speichern(self.bot, nd)

        # DM: genehmigt
        member = interaction.guild.get_member(self.uid)
        if member:
            await dm_urlaub_genehmigt(interaction.guild, member, self.dauer, end_ts)

        e = interaction.message.embeds[0]
        e.color = discord.Color.green()
        e.add_field(name="✅ Genehmigt von", value=f"{interaction.user.mention} — <t:{int(jetzt)}:F>", inline=False)
        await interaction.message.edit(embed=e, view=None)
        await interaction.response.send_message("✅ Antrag genehmigt.", ephemeral=True)

    @discord.ui.button(label="<:3518crossmark:1477410571266818219> Ablehnen", style=discord.ButtonStyle.danger)
    async def ablehnen(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.bot.ist_leitungsebene(interaction.user):
            return await interaction.response.send_message("Fehler: `Leitungsebene` benötigt!", ephemeral=True)

        # DM: abgelehnt
        member = interaction.guild.get_member(self.uid)
        if member:
            await dm_urlaub_abgelehnt(interaction.guild, member, self.dauer)

        e = interaction.message.embeds[0]
        e.color = discord.Color.red()
        e.add_field(name="__Bearbeiter__", value=f"> <:7549member:1477410605240549637> - {interaction.user.mention}", inline=False)
        await interaction.message.edit(embed=e, view=None)
        await interaction.response.send_message("Antrag abgelehnt.", ephemeral=True)


# ============================================================
# URLAUBS ADMIN VIEW — volle Verwaltung
# ============================================================
class UrlaubsAdminView(discord.ui.View):
    def __init__(self, ziel: discord.Member, bot):
        super().__init__(timeout=None)
        self.ziel = ziel
        self.bot  = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.bot.ist_leitungsebene(interaction.user):
            await interaction.response.send_message("Fehler: `Leitungsebene` benötigt!", ephemeral=True)
            return False
        return True

    @discord.ui.select(
        placeholder="Urlaub verwalten",
        options=[
            discord.SelectOption(label="Urlaub starten",         value="starten",   description="Neuen Urlaub für diesen User starten",    emoji="▶️"),
            discord.SelectOption(label="Aktiven Urlaub beenden", value="beenden",   description="Laufenden Urlaub vorzeitig beenden",       emoji="⏹️"),
            discord.SelectOption(label="Urlaub verlängern",      value="verlaengern",description="Aktiven Urlaub verlängern",               emoji="⏩"),
            discord.SelectOption(label="Urlaub löschen",         value="loeschen",  description="Alle Urlaubsdaten löschen",                emoji="🗑️"),
        ],
        row=0
    )
    async def urlaub_dropdown(self, interaction: discord.Interaction, select: discord.ui.Select):
        aktion = select.values[0]

        if aktion == "starten":
            return await interaction.response.send_modal(AdminUrlaubStartModal(self.ziel, self.bot))

        if aktion == "beenden":
            return await interaction.response.send_modal(AdminUrlaubBeendenModal(self.ziel, self.bot))

        if aktion == "verlaengern":
            return await interaction.response.send_modal(AdminUrlaubVerlaengernModal(self.ziel, self.bot))

        if aktion == "loeschen":
            uid_str = str(self.ziel.id)
            db = self.bot.load_json(self.bot.LEAVE_FILE)
            db.pop(uid_str, None)
            self.bot.save_json(self.bot.LEAVE_FILE, db)
            nd = nd_laden(self.bot, uid_str)
            nd[uid_str]["urlaubstage"] = 0
            nd_speichern(self.bot, nd)
            await interaction.response.send_message(f"Alle Urlaubsdaten von {self.ziel.mention} gelöscht!", ephemeral=True)

    @discord.ui.button(label="Erweiterte Historie", style=discord.ButtonStyle.secondary, row=1)
    async def extended_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid       = str(self.ziel.id)
        db        = self.bot.load_json(self.bot.LEAVE_FILE)
        eintraege = db.get(uid, {}).get("eintraege", [])
        e = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
        e.set_author(name=f"Urlaubsverwaltung: @{self.ziel.name}", icon_url=self.ziel.display_avatar.url)
        e.title = "Urlaubsverwaltung"
        if eintraege:
            zeilen = []
            for i, entry in enumerate(eintraege, 1):
                ts     = entry.get("zeitstempel", time.time())
                dt     = datetime.fromtimestamp(ts, tz=timezone.utc)
                status = entry.get("status", "ausstehend")
                icon   = "✅" if status == "genehmigt" else "❌" if status == "abgelehnt" else "⏳"
                zeilen.append(f"{i}. {dt.strftime('%d. %B %Y um %H:%M')} [{entry.get('dauer','?')}] {icon}")
            e.add_field(name="Alle Einträge", value="\n".join(zeilen), inline=False)
        else:
            e.add_field(name="Alle Einträge", value="Keine Einträge.", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)


class AdminUrlaubStartModal(discord.ui.Modal, title="Urlaub starten"):
    dauer_feld = discord.ui.TextInput(label="Dauer", placeholder="1d  |  2w  |  1m", required=True, max_length=10)
    grund      = discord.ui.TextInput(label="Begründung (optional)", required=False, max_length=300)

    def __init__(self, ziel: discord.Member, bot):
        super().__init__()
        self.ziel = ziel
        self.bot  = bot

    async def on_submit(self, interaction: discord.Interaction):
        uid_str  = str(self.ziel.id)
        jetzt    = time.time()
        dur_sek  = dauer_zu_sekunden(self.dauer_feld.value)
        end_ts   = int(jetzt + dur_sek)
        start_ts = int(jetzt)

        db = self.bot.load_json(self.bot.LEAVE_FILE)
        if uid_str not in db: db[uid_str] = {"eintraege": [], "aktiv": []}
        db[uid_str]["eintraege"].append({
            "dauer": self.dauer_feld.value, "zeitstempel": jetzt, "start_zeitstempel": start_ts,
            "end_zeitstempel": end_ts, "status": "genehmigt"
        })
        db[uid_str]["aktiv"].append({
            "dauer": self.dauer_feld.value, "start_zeitstempel": start_ts,
            "end_zeitstempel": end_ts, "benutzername": self.ziel.display_name
        })
        self.bot.save_json(self.bot.LEAVE_FILE, db)
        nd = nd_laden(self.bot, uid_str)
        nd[uid_str]["urlaubstage"] = nd[uid_str].get("urlaubstage", 0) + dauer_zu_tage(self.dauer_feld.value)
        nd_speichern(self.bot, nd)

        # DM senden
        await dm_urlaub_genehmigt(interaction.guild, self.ziel, self.dauer_feld.value, end_ts)

        dt_end = datetime.fromtimestamp(end_ts, tz=timezone.utc)
        await interaction.response.send_message(
            f"✅ Urlaub für {self.ziel.mention} gestartet.\n"
            f"Endet am **{dt_end.strftime('%d. %B %Y um %H:%M')}** [{self.dauer_feld.value}].",
            ephemeral=True)


class AdminUrlaubBeendenModal(discord.ui.Modal, title="Aktiven Urlaub beenden"):
    bestaetigung = discord.ui.TextInput(
        label="Bestätigung",
        placeholder="Gib 'BEENDEN' ein um zu bestätigen",
        required=True, max_length=7
    )
    def __init__(self, ziel: discord.Member, bot):
        super().__init__()
        self.ziel = ziel
        self.bot  = bot

    async def on_submit(self, interaction: discord.Interaction):
        if self.bestaetigung.value.upper() != "BEENDEN":
            return await interaction.response.send_message("Fehler: `Bestätigungswort` fehlerhaft!", ephemeral=True)
        uid_str = str(self.ziel.id)
        db      = self.bot.load_json(self.bot.LEAVE_FILE)
        if uid_str not in db or not db[uid_str].get("aktiv"):
            return await interaction.response.send_message("Fehler: `Urlaub` nicht aktiv!", ephemeral=True)

        # Ersten aktiven Urlaub beenden
        aktive = db[uid_str].get("aktiv", [])
        if aktive:
            eintrag    = aktive[0]
            start_ts   = eintrag.get("start_zeitstempel", int(time.time()))
            db[uid_str]["aktiv"] = aktive[1:]
            self.bot.save_json(self.bot.LEAVE_FILE, db)
            # DM: beendet
            await dm_urlaub_beendet(interaction.guild, self.ziel, start_ts)
            await interaction.response.send_message(f"Urlaub von {self.ziel.mention} beendet!", ephemeral=True)
        else:
            await interaction.response.send_message("Fehler: `Urlaub` nicht aktiv!", ephemeral=True)


class AdminUrlaubVerlaengernModal(discord.ui.Modal, title="Urlaub verlängern"):
    zusatz = discord.ui.TextInput(
        label="Verlängerung",
        placeholder="1d  |  1w  |  1m",
        required=True, max_length=10
    )
    def __init__(self, ziel: discord.Member, bot):
        super().__init__()
        self.ziel = ziel
        self.bot  = bot

    async def on_submit(self, interaction: discord.Interaction):
        uid_str = str(self.ziel.id)
        db      = self.bot.load_json(self.bot.LEAVE_FILE)
        aktive  = db.get(uid_str, {}).get("aktiv", [])
        if not aktive:
            return await interaction.response.send_message("Fehler: `Urlaub` nicht aktiv!", ephemeral=True)

        zusatz_sek = dauer_zu_sekunden(self.zusatz.value)
        aktive[0]["end_zeitstempel"] = aktive[0].get("end_zeitstempel", int(time.time())) + zusatz_sek
        db[uid_str]["aktiv"] = aktive
        self.bot.save_json(self.bot.LEAVE_FILE, db)

        neues_ende = aktive[0]["end_zeitstempel"]
        # DM senden
        await dm_urlaub_genehmigt(interaction.guild, self.ziel, self.zusatz.value, neues_ende)
        await interaction.response.send_message(
            f"✅ Urlaub von {self.ziel.mention} um **{self.zusatz.value}** verlängert.\n"
            f"Neues Ende: <t:{neues_ende}:F>", ephemeral=True)


# ============================================================
# COG
# ============================================================
class ShiftCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.shift_group = app_commands.Group(name="shift", description="Schichtverwaltung")
        self.leave_group = app_commands.Group(name="leave", description="Urlaubsverwaltung")

        # ── /shift manage ─────────────────────────────────────
        @self.shift_group.command(name="manage", description="Öffnet deinen persönlichen Schicht-Manager")
        async def shift_manage(interaction: discord.Interaction):
            if not bot.ist_mitarbeiter(interaction.user):
                return await interaction.response.send_message("Fehler: `Mitarbeiter` benötigt!", ephemeral=True)
            uid     = str(interaction.user.id)
            alle    = shifts_laden(bot)
            s       = alle.get(uid)
            status  = s.get("status", "inaktiv") if s else "inaktiv"
            view    = ShiftView(interaction.user.id, bot, status)
            embed   = shift_embed_erstellen(bot, interaction.user, status)
            await interaction.response.send_message(embed=embed, view=view)

        # ── /shift active ──────────────────────────────────────
        @self.shift_group.command(name="active", description="Zeigt alle aktiven Schichten")
        async def shift_active(interaction: discord.Interaction):
            if not bot.ist_mitarbeiter(interaction.user):
                return await interaction.response.send_message("Fehler: `Mitarbeiter` benötigt!", ephemeral=True)
            alle_shifts = shifts_laden(bot)
            guild       = interaction.guild
            e = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
            if guild and guild.icon:
                e.set_author(name=guild.name, icon_url=guild.icon.url)
                e.set_thumbnail(url=guild.icon.url)
            aktive = {uid: s for uid, s in alle_shifts.items() if s.get("status") in ("aktiv", "pausiert")}
            if not aktive:
                e.add_field(name="🕐 Aktive Schichten", value="Es gibt keine aktiven Schichten.", inline=False)
            else:
                zeilen = []
                for uid, s in aktive.items():
                    icon = "🟢" if s.get("status") == "aktiv" else "🟡"
                    zeilen.append(f"{icon} **{s.get('benutzername', f'<@{uid}>')}** • {dauer_formatieren(aktuelle_shift_sekunden(s))}")
                e.add_field(name="🕐 Aktive Schichten", value="\n".join(zeilen), inline=False)
            await interaction.response.send_message(embed=e)

        # ── /shift leaderboard ─────────────────────────────────
        @self.shift_group.command(name="leaderboard", description="Zeigt das Schicht-Leaderboard")
        async def shift_leaderboard(interaction: discord.Interaction):
            if not bot.ist_mitarbeiter(interaction.user):
                return await interaction.response.send_message("Fehler: `Mitarbeiter` benötigt!", ephemeral=True)
            nd_alle  = bot.load_json(bot.USERS_FILE)
            guild    = interaction.guild
            sortiert = sorted(
                [(uid, d) for uid, d in nd_alle.items() if d.get("gesamt_shift_sekunden", 0) > 0],
                key=lambda x: x[1].get("gesamt_shift_sekunden", 0), reverse=True
            )
            e = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
            if guild and guild.icon:
                e.set_author(name=guild.name, icon_url=guild.icon.url)
                e.set_thumbnail(url=guild.icon.url)
            e.title = "Shift Leaderboard"
            if not sortiert:
                e.description = "Noch keine Schichtdaten vorhanden."
            else:
                zeilen = []
                for i, (uid, daten) in enumerate(sortiert[:10], 1):
                    m    = guild.get_member(int(uid)) if guild else None
                    name = m.mention if m else daten.get("benutzername", f"<@{uid}>")
                    zeilen.append(f"{i}. {name} • {dauer_formatieren(daten.get('gesamt_shift_sekunden', 0))}")
                e.description = "\n".join(zeilen)
                e.add_field(name="\u200b", value="Alle Schichttypen", inline=False)
            await interaction.response.send_message(embed=e)

        # ── /shift admin ───────────────────────────────────────
        @self.shift_group.command(name="admin", description="Admin-Schichtmanager für einen User")
        @app_commands.describe(user="Ziel-User")
        async def shift_admin(interaction: discord.Interaction, user: discord.Member):
            if not bot.ist_leitungsebene(interaction.user):
                return await interaction.response.send_message("Fehler: `Leitungsebene` benötigt!", ephemeral=True)
            view = ShiftAdminView(user, bot)
            await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

        # ── /leave manage ──────────────────────────────────────
        @self.leave_group.command(name="manage", description="Verwalte deinen Urlaub")
        async def leave_manage(interaction: discord.Interaction):
            if not bot.ist_mitarbeiter(interaction.user):
                return await interaction.response.send_message("Fehler: `Mitarbeiter` benötigt!", ephemeral=True)
            uid       = str(interaction.user.id)
            db        = bot.load_json(bot.LEAVE_FILE)
            eintraege = db.get(uid, {}).get("eintraege", [])
            e = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
            e.set_author(name=f"@{interaction.user.name}", icon_url=interaction.user.display_avatar.url)
            e.title = "Urlaubsverwaltung"
            if eintraege:
                zeilen = []
                for i, entry in enumerate(eintraege[-3:], 1):
                    ts = entry.get("zeitstempel", time.time())
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    zeilen.append(f"{i}. {dt.strftime('%d. %B %Y um %H:%M')} [{entry.get('dauer','?')}]")
                e.add_field(name="Letzte Einträge", value="\n".join(zeilen), inline=False)
            else:
                e.add_field(name="Letzte Einträge", value="Keine Urlaubseinträge.", inline=False)
            await interaction.response.send_message(embed=e, view=UrlaubsView(bot), ephemeral=True)

        # ── /leave active ──────────────────────────────────────
        @self.leave_group.command(name="active", description="Zeigt alle aktiven Urlaubsabwesenheiten")
        async def leave_active(interaction: discord.Interaction):
            if not bot.ist_mitarbeiter(interaction.user):
                return await interaction.response.send_message("Fehler: `Mitarbeiter` benötigt!", ephemeral=True)
            db    = bot.load_json(bot.LEAVE_FILE)
            guild = interaction.guild
            jetzt = time.time()
            e = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
            if guild and guild.icon:
                e.set_author(name=guild.name, icon_url=guild.icon.url)
                e.set_thumbnail(url=guild.icon.url)
            e.title = "Aktive Urlaubsabwesenheiten"
            aktive = []
            for uid, daten in db.items():
                for entry in daten.get("aktiv", []):
                    end_ts = entry.get("end_zeitstempel", 0)
                    if end_ts > jetzt:
                        m    = guild.get_member(int(uid)) if guild else None
                        name = m.mention if m else entry.get("benutzername", f"<@{uid}>")
                        dt_end = datetime.fromtimestamp(end_ts, tz=timezone.utc)
                        aktive.append((name, dt_end, end_ts - jetzt))
            if not aktive:
                e.description = "Es gibt keine aktiven Urlaubsabwesenheiten."
            else:
                zeilen = []
                for i, (name, dt_end, rest) in enumerate(aktive, 1):
                    zeilen.append(f"{i}. {name} • Endet {dt_end.strftime('%d. %B %Y um %H:%M')} [{dauer_relativ(rest)}]")
                e.description = "\n".join(zeilen)
            await interaction.response.send_message(embed=e)

        # ── /leave admin ───────────────────────────────────────
        @self.leave_group.command(name="admin", description="Urlaubsverwaltung für einen User (Leitungsebene)")
        @app_commands.describe(user="Ziel-User")
        async def leave_admin(interaction: discord.Interaction, user: discord.Member):
            if not bot.ist_leitungsebene(interaction.user):
                return await interaction.response.send_message("Fehler: `Leitungsebene` benötigt!", ephemeral=True)
            uid       = str(user.id)
            db        = bot.load_json(bot.LEAVE_FILE)
            eintraege = db.get(uid, {}).get("eintraege", [])
            e = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
            e.set_author(name=f"Urlaubsverwaltung: @{user.name}", icon_url=user.display_avatar.url)
            e.title = "Urlaubsverwaltung"

            # Aktiver Urlaub
            jetzt  = time.time()
            aktive = [a for a in db.get(uid, {}).get("aktiv", []) if a.get("end_zeitstempel", 0) > jetzt]
            if aktive:
                a      = aktive[0]
                end_ts = a.get("end_zeitstempel", 0)
                dt_end = datetime.fromtimestamp(end_ts, tz=timezone.utc)
                e.add_field(
                    name="📍 Aktuell aktiv",
                    value=f"Endet am **{dt_end.strftime('%d. %B %Y um %H:%M')}** (noch {dauer_relativ(end_ts - jetzt)})",
                    inline=False
                )

            if eintraege:
                zeilen = []
                for i, entry in enumerate(eintraege[-3:], 1):
                    ts     = entry.get("zeitstempel", time.time())
                    dt     = datetime.fromtimestamp(ts, tz=timezone.utc)
                    status = entry.get("status", "ausstehend")
                    icon   = "✅" if status == "genehmigt" else "❌" if status == "abgelehnt" else "⏳"
                    zeilen.append(f"{i}. {dt.strftime('%d. %B %Y um %H:%M')} [{entry.get('dauer','?')}] {icon}")
                e.add_field(name="Letzte Einträge", value="\n".join(zeilen), inline=False)
            else:
                e.add_field(name="Letzte Einträge", value="Keine Einträge.", inline=False)

            await interaction.response.send_message(embed=e, view=UrlaubsAdminView(user, bot), ephemeral=True)

    async def cog_load(self):
        self.bot.tree.add_command(self.shift_group)
        self.bot.tree.add_command(self.leave_group)

    async def cog_unload(self):
        self.bot.tree.remove_command("shift")
        self.bot.tree.remove_command("leave")


async def setup(bot: commands.Bot):
    await bot.add_cog(ShiftCog(bot))

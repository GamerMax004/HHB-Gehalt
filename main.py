import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import asyncio
import zipfile
import io
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

ADMIN_USER_IDS = [
    1211683189186105434,  # GamerMax
]

BOT_TOKEN = os.getenv("DISCORD_TOKEN")

DB_PATH     = "database"
CONFIG_FILE = f"{DB_PATH}/config.json"
SHIFTS_FILE = f"{DB_PATH}/shifts.json"
USERS_FILE  = f"{DB_PATH}/users.json"
SALARY_FILE = f"{DB_PATH}/salary.json"
LEAVE_FILE  = f"{DB_PATH}/leave.json"

BACKUP_DATEIEN = {
    "config.json":  CONFIG_FILE,
    "shifts.json":  SHIFTS_FILE,
    "users.json":   USERS_FILE,
    "salary.json":  SALARY_FILE,
    "leave.json":   LEAVE_FILE,
}

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot laeuft!")
    def log_message(self, format, *args):
        pass

def keep_alive():
    port = int(os.getenv("PORT", 8080))  # FIX: Render gibt PORT als Env-Variable vor
    server = HTTPServer(("0.0.0.0", port), KeepAliveHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[Keep Alive] HTTP-Server gestartet auf Port {port}")

def load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def init_database():
    if not os.path.exists(DB_PATH):
        os.makedirs(DB_PATH)
    defaults = {
        CONFIG_FILE: {
            "rollen":  {"leitungsebene": [], "mitarbeiter": []},
            "kanaele": {"panel": None, "dokumentationen": None, "urlaubsantraege": None, "backup": None},
            "panel_nachricht_id": None
        },
        SHIFTS_FILE: {},
        USERS_FILE:  {},
        SALARY_FILE: {"rollen": {}},
        LEAVE_FILE:  {},
    }
    for path, default in defaults.items():
        if not os.path.exists(path):
            save_json(path, default)
            print(f"[DB] {path} erstellt.")

def ist_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS

def ist_leitungsebene(member: discord.Member) -> bool:
    if ist_admin(member.id):
        return True
    config = load_json(CONFIG_FILE)
    ids = config.get("rollen", {}).get("leitungsebene", [])
    return any(str(r.id) in ids for r in member.roles)

def ist_mitarbeiter(member: discord.Member) -> bool:
    if ist_leitungsebene(member):
        return True
    config = load_json(CONFIG_FILE)
    ids = config.get("rollen", {}).get("mitarbeiter", [])
    return any(str(r.id) in ids for r in member.roles)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

bot.load_json         = load_json
bot.save_json         = save_json
bot.ist_admin         = ist_admin
bot.ist_leitungsebene = ist_leitungsebene
bot.ist_mitarbeiter   = ist_mitarbeiter
bot.CONFIG_FILE       = CONFIG_FILE
bot.SHIFTS_FILE       = SHIFTS_FILE
bot.USERS_FILE        = USERS_FILE
bot.SALARY_FILE       = SALARY_FILE
bot.LEAVE_FILE        = LEAVE_FILE
bot.ADMIN_USER_IDS    = ADMIN_USER_IDS

async def backup_senden(kanal: discord.TextChannel):
    jetzt           = datetime.now(timezone.utc)
    guild           = kanal.guild
    zeitstempel_str = jetzt.strftime("%Y%m%d_%H%M%S")

    zip_buf = io.BytesIO()
    anzahl  = 0
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dateiname, pfad in BACKUP_DATEIEN.items():
            if os.path.exists(pfad):
                basis = dateiname.replace(".json", "")
                zf.write(pfad, arcname=f"{basis}_{zeitstempel_str}.json")
                anzahl += 1
    zip_buf.seek(0)

    embed = discord.Embed(color=discord.Color.from_rgb(44, 47, 51), timestamp=jetzt)
    if guild and guild.icon:
        embed.set_author(name=guild.name, icon_url=guild.icon.url)
    embed.title       = "Automatisches Datenbank-Backup"
    embed.description = "Alle Datenbankdateien wurden als ZIP-Archiv gesichert."
    embed.add_field(name="__Zeitpunkt__", value=f"<t:{int(jetzt.timestamp())}:F>", inline=False)
    embed.add_field(name="__Dateien__",   value="\n".join(f"> <:2141file:1477410565285609562> - `{n}`" for n in BACKUP_DATEIEN), inline=False)
    embed.set_footer(text="Nächstes Backup in 24 Stunden")

    zip_dateiname = f"backup_{zeitstempel_str}.zip"
    await kanal.send(embed=embed, file=discord.File(zip_buf, filename=zip_dateiname))
    print(f"[Backup] {anzahl} Dateien als {zip_dateiname} in #{kanal.name} gesendet.")

async def backup_task():
    await bot.wait_until_ready()
    print("[Backup] Task gestartet.")
    while not bot.is_closed():
        await asyncio.sleep(24 * 60 * 60)
        config   = load_json(CONFIG_FILE)
        kanal_id = config.get("kanaele", {}).get("backup")
        if not kanal_id:
            continue
        kanal = None
        for guild in bot.guilds:
            kanal = guild.get_channel(int(kanal_id))
            if kanal:
                break
        if not kanal:
            continue
        try:
            await backup_senden(kanal)
        except Exception as e:
            print(f"[Backup] Fehler: {e}")

@bot.event
async def on_ready():
    print(f"[Bot] Eingeloggt als {bot.user} (ID: {bot.user.id})")
    # FIX: Extensions werden NACH dem Login geladen
    for ext in ("shift", "tickets", "gehalt"):
        try:
            await bot.load_extension(ext)
            print(f"[Bot] Extension '{ext}' geladen.")
        except Exception as e:
            print(f"[Bot] Fehler beim Laden von '{ext}': {e}")
    try:
        synced = await bot.tree.sync()
        print(f"[Bot] {len(synced)} Slash-Commands synchronisiert.")
    except Exception as e:
        print(f"[Bot] Sync-Fehler: {e}")
    asyncio.create_task(backup_task())

# ─────────────────────────────────────────────
#  /reload  –  Backup-ZIP wieder einspielen
# ─────────────────────────────────────────────
@bot.tree.command(name="reload", description="Spielt ein Datenbank-Backup (ZIP) wieder ein (nur Admins)")
@app_commands.describe(backup_zip="Die Backup-ZIP-Datei, die eingespielt werden soll")
async def reload_backup(interaction: discord.Interaction, backup_zip: discord.Attachment):
    # Berechtigungsprüfung
    if not ist_admin(interaction.user.id):
        return await interaction.response.send_message(
            "Fehler: `Administrator` benötigt!", ephemeral=True
        )

    # Nur ZIP erlauben
    if not backup_zip.filename.endswith(".zip"):
        return await interaction.response.send_message(
            "Fehler: Bitte nur `.zip`-Dateien hochladen!", ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)

    try:
        # ZIP herunterladen
        zip_bytes = await backup_zip.read()
        zip_buf   = io.BytesIO(zip_bytes)

        eingespielt  = []
        uebersprungen = []
        fehler        = []

        with zipfile.ZipFile(zip_buf, "r") as zf:
            namen = zf.namelist()

            for dateiname_in_zip in namen:
                # Basis-Name ermitteln (z.B. "config_20240101_120000.json" → "config.json")
                basis = dateiname_in_zip.split("_")[0] + ".json"

                if basis not in BACKUP_DATEIEN:
                    uebersprungen.append(dateiname_in_zip)
                    continue

                ziel_pfad = BACKUP_DATEIEN[basis]

                try:
                    inhalt = zf.read(dateiname_in_zip)
                    # JSON-Validierung
                    json.loads(inhalt)
                    # Sicherstellen, dass der Ordner existiert
                    os.makedirs(os.path.dirname(ziel_pfad), exist_ok=True)
                    with open(ziel_pfad, "wb") as f:
                        f.write(inhalt)
                    eingespielt.append(f"`{basis}`")
                    print(f"[Reload] {basis} wiederhergestellt aus {dateiname_in_zip}")
                except json.JSONDecodeError:
                    fehler.append(f"`{dateiname_in_zip}` (ungültiges JSON)")
                except Exception as e:
                    fehler.append(f"`{dateiname_in_zip}` ({e})")

        # Ergebnis-Embed
        jetzt = datetime.now(timezone.utc)
        embed = discord.Embed(color=discord.Color.from_rgb(44, 47, 51), timestamp=jetzt)
        if interaction.guild and interaction.guild.icon:
            embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url)
        embed.title = "Backup eingespielt!"

        if eingespielt:
            embed.add_field(
                name="__Wiederhergestellt__",
                value="\n".join(f"> <:2141file:1477410565285609562> - {d}" for d in eingespielt),
                inline=False
            )
        if uebersprungen:
            embed.add_field(
                name="__Übersprungen__ (unbekannte Dateien)",
                value="\n".join(f"> ⚠️ `{d}`" for d in uebersprungen),
                inline=False
            )
        if fehler:
            embed.add_field(
                name="__Fehler__",
                value="\n".join(f"> ❌ {d}" for d in fehler),
                inline=False
            )
        if not eingespielt and not fehler:
            embed.description = "⚠️ Keine bekannten Datenbankdateien in der ZIP gefunden."

        embed.set_footer(text=f"ZIP: {backup_zip.filename}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    except zipfile.BadZipFile:
        await interaction.followup.send(
            "Fehler: Die hochgeladene Datei ist keine gültige ZIP-Datei!", ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(f"Unbekannter Fehler: `{e}`", ephemeral=True)

# ─────────────────────────────────────────────
#  Konfigurationsgruppe
# ─────────────────────────────────────────────
konfiguriere_group = app_commands.Group(name="konfiguriere", description="Bot-Konfiguration (nur Admins)")

@konfiguriere_group.command(name="rolle", description="Setzt eine Rolle für eine Sicherheitsstufe")
@app_commands.describe(stufe="Sicherheitsstufe", rolle="Die Rolle")
@app_commands.choices(stufe=[
    app_commands.Choice(name="Leitungsebene", value="leitungsebene"),
    app_commands.Choice(name="Mitarbeiter",   value="mitarbeiter"),
])
async def konfiguriere_rolle(interaction: discord.Interaction, stufe: app_commands.Choice[str], rolle: discord.Role):
    if not ist_admin(interaction.user.id):
        return await interaction.response.send_message("Fehler: `Administrator` benötigt!", ephemeral=True)
    config = load_json(CONFIG_FILE)
    if str(rolle.id) not in config["rollen"][stufe.value]:
        config["rollen"][stufe.value].append(str(rolle.id))
    save_json(CONFIG_FILE, config)
    embed = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
    if interaction.guild and interaction.guild.icon:
        embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url)
    embed.title       = "Konfiguration gespeichert!"
    embed.description = ""
    embed.add_field(name="__Rolle__", value=f"> <:4748ticket:1477410582691840140> - {rolle.mention}", inline=False)
    embed.add_field(name="__Berechtigung__", value=f"> <:7842privacy:1477410613415248004> - {stufe.name}", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@konfiguriere_group.command(name="kanal", description="Setzt einen Kanal für eine Funktion")
@app_commands.describe(funktion="Funktion des Kanals", kanal="Der Kanal")
@app_commands.choices(funktion=[
    app_commands.Choice(name="Panel",           value="panel"),
    app_commands.Choice(name="Dokumentationen", value="dokumentationen"),
    app_commands.Choice(name="Urlaubsanträge",  value="urlaubsantraege"),
    app_commands.Choice(name="Backup",          value="backup"),
])
async def konfiguriere_kanal(interaction: discord.Interaction, funktion: app_commands.Choice[str], kanal: discord.TextChannel):
    if not ist_admin(interaction.user.id):
        return await interaction.response.send_message("Fehler: `Administrator` benötigt!", ephemeral=True)
    config = load_json(CONFIG_FILE)
    config["kanaele"].setdefault("backup", None)
    config["kanaele"][funktion.value] = str(kanal.id)
    save_json(CONFIG_FILE, config)
    embed = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
    if interaction.guild and interaction.guild.icon:
        embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url)
    embed.title       = "Konfiguration gespeichert!"
    embed.description = ""
    if funktion.value == "backup":
        embed.add_field(name="__Kanal__", value=f"> <:1041searchthreads:1477410555726659775> - {kanal.mention}", inline=False)
        embed.add_field(name="__Funktion__", value=f"> <:1072automod:1477410557371089019> - {funktion.name}", inline=False)
        embed.add_field(name="__Hinweis__", value="> Erstes automatisches Backup in **24 Stunden**. Alternativ kann für ein Backup auch folgender Befehl verwendet werden:\n> <:8586slashcommand:1477410626769915984> - </backup:1477401421950484693>", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)
    if funktion.value == "panel":
        from tickets import panel_embed_senden
        await panel_embed_senden(bot, kanal, config)

bot.tree.add_command(konfiguriere_group)

@bot.tree.command(name="backup", description="Sendet sofort ein Datenbank-Backup als ZIP (nur Admins)")
async def backup_manuell(interaction: discord.Interaction):
    if not ist_admin(interaction.user.id):
        return await interaction.response.send_message("Fehler: `Administrator` benötigt!", ephemeral=True)
    config   = load_json(CONFIG_FILE)
    kanal_id = config.get("kanaele", {}).get("backup")
    if not kanal_id:
        return await interaction.response.send_message("Fehler: `Backup-Kanal` nicht konfiguriert!", ephemeral=True)
    kanal = interaction.guild.get_channel(int(kanal_id))
    if not kanal:
        return await interaction.response.send_message("Fehler: `Backup-Kanal` nicht gefunden!", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    try:
        await backup_senden(kanal)
        embed = discord.Embed(color=discord.Color.from_rgb(44, 47, 51))
        if interaction.guild and interaction.guild.icon:
            embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url)
        embed.title       = "Backup gesendet!"
        embed.description = f"Alle Datenbankdateien wurden als ZIP-Datenpaket in {kanal.mention} gesichert."
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Fehler: `{e}`", ephemeral=True)

# ─────────────────────────────────────────────
#  Start
# ─────────────────────────────────────────────
async def main():
    init_database()
    keep_alive()
    async with bot:
        await bot.start(BOT_TOKEN)  # FIX: Extensions werden in on_ready geladen

if __name__ == "__main__":
    asyncio.run(main())

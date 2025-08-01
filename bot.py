import discord
from discord.ext import commands, tasks
import aiosqlite
import datetime
import os
from dotenv import load_dotenv
from pathlib import Path

# ENV-Variablen laden
load_dotenv()


TOKEN = os.getenv("DISCORD_TOKEN")


intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

voice_states = {}
DB_PATH = Path("activity.db")


@bot.event
async def on_ready():
    print(f"✅ Bot ist online als {bot.user}")
    await init_db()
    update_nicknames.start()

# Datenbank initialisieren
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                user_id INTEGER PRIMARY KEY,
                seconds INTEGER DEFAULT 0
            )
        """)
        await db.commit()
    print("📁 Datenbank geprüft oder erstellt.")

# Voice Join / Leave Tracker
@bot.event
async def on_voice_state_update(member, before, after):
    user_id = member.id

    if before.channel is None and after.channel is not None:
        voice_states[user_id] = datetime.datetime.utcnow()
        print(f"🎤 {member.display_name} ist dem Voice beigetreten.")

        # Direkt Eintrag anlegen, wenn nicht vorhanden
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO activity (user_id, seconds) VALUES (?, ?);",
                (member.id, 0)
            )
            await db.commit()
            print(f"🆕 Benutzer {member.display_name} zur Datenbank hinzugefügt.")

    elif before.channel is not None and after.channel is None:
        if user_id in voice_states:
            join_time = voice_states.pop(user_id)
            duration = datetime.datetime.utcnow() - join_time
            seconds = int(duration.total_seconds())
            print(f"⏳ {member.display_name} war {seconds} Sekunden im Voice.")

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO activity (user_id, seconds) VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET seconds = seconds + ?;
                    """,
                    (user_id, seconds, seconds)
                )
                await db.commit()
                print(f"✅ Voice-Zeit gespeichert: +{seconds} Sek. für {member.display_name}")


# Nickname-Updater (läuft jede Minute)
@tasks.loop(minutes=1)
async def update_nicknames():
    print("🔄 Starte Nickname-Update-Loop...")
    for guild in bot.guilds:
        async with aiosqlite.connect(DB_PATH) as db:
            for member in guild.members:
                if member.bot:
                    continue  # Bots überspringen

                # Stelle sicher, dass der Member in der DB ist
                await db.execute(
                    "INSERT OR IGNORE INTO activity (user_id, seconds) VALUES (?, ?);",
                    (member.id, 0)
                )

                # Lade aktuelle Zeit
                async with db.execute("SELECT seconds FROM activity WHERE user_id = ?", (member.id,)) as cursor:
                    row = await cursor.fetchone()

                if not row:
                    print(f"⚠️ Kein DB-Eintrag für {member.display_name} gefunden – übersprungen.")
                    continue

                seconds = row[0]
                flames = seconds // 3600

                current_nick = member.nick or member.name
                base = current_nick.split(" (🔥")[0]
                new_nick = f"{base} (🔥{flames})"

                print(f"🧪 {member.display_name}: current={current_nick}, new={new_nick}")

                if current_nick != new_nick:
                    try:
                        await member.edit(nick=new_nick)
                        print(f"🔥 Nickname geändert für {member.display_name} → {new_nick}")
                    except discord.Forbidden:
                        print(f"❌ [FORBIDDEN] Bot hat keine Berechtigung, {member.display_name} zu ändern.")
                    except discord.HTTPException as e:
                        print(f"⚠️ HTTPException: {e.status} - {e.text}")
                    except Exception as e:
                        print(f"❗ Unbekannter Fehler bei {member.display_name}: {type(e).__name__}: {e}")
                else:
                    print(f"✔️ {member.display_name} hat bereits den richtigen Nickname.")
            await db.commit()

# !stats Befehl
@bot.command(name="stats")
async def stats(ctx):
    user_id = ctx.author.id

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT seconds FROM activity WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()

    if row:
        seconds = row[0]
        minutes = seconds // 60
        hours = seconds // 3600
        flames = seconds // 3600  # 🔥 1 Flamme = 1 Stunde
        print(f"📊 {ctx.author.display_name} hat {seconds} Sekunden Voice-Zeit.")
        await ctx.send(
            f"⏱️ Du warst **{hours} Stunden** / **{minutes} Minuten** im Voice.\n"
            f"🔥 Flammen-Level: `{flames}`"
        )
    else:
        await ctx.send("🔍 Du hast noch keine Voice-Zeit gesammelt.")
        print(f"📊 {ctx.author.display_name} hat noch keinen Eintrag in der Datenbank.")



@bot.command(name="leaderboard")
async def leaderboard(ctx):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, seconds FROM activity ORDER BY seconds DESC LIMIT 10"
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await ctx.send("📭 Noch keine Daten für das Leaderboard.")
        return

    lines = []
    for i, (user_id, seconds) in enumerate(rows, start=1):
        member = ctx.guild.get_member(user_id)
        name = member.display_name if member else f"Unbekannt ({user_id})"
        minutes = seconds // 60
        flames = seconds // 3600  # 🔥 1 Flamme = 1 Stunde

        lines.append(f"**{i}.** {name} – {minutes} Min ⏱️ / 🔥 {flames}")

    embed = discord.Embed(
        title="🏆 Voice Leaderboard",
        description="\n".join(lines),
        color=discord.Color.orange()
    )

    await ctx.send(embed=embed)


# Bot starten
bot.run(TOKEN)
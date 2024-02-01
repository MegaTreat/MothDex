countryballs = {
"ball name": "ball url"
"ball name 2": "ball url 2"
# add more if yoooooou want, this is just an test.
}

import discord
from discord.ext import commands, tasks
from discord import app_commands
import random, asyncio, yaml, os, requests, time, json
from typing import Literal, Optional
import sqlite3

with open("settings.yml") as f:
    settings = yaml.load(f, Loader=yaml.FullLoader)

token = settings["bot-token"]
prefix = settings["text-prefix"]
collectibles_name = settings["collectibles-name"]
slash_command_name = settings["players-group-cog-name"]
bot_name = settings["bot-name"]

bot = commands.Bot(command_prefix=prefix, intents=discord.Intents.all())
bot.remove_command("help")
tree = bot.tree

caught_balls = {}

conn = sqlite3.connect("caught_balls.db")
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS caught_balls (
        user_id INTEGER,
        url TEXT,
        name TEXT,
        timestamp REAL,
        shiny_status TEXT
    )
""")

def add_caught_ball(user_id, url, name, timestamp, shiny_status):
    cursor.execute("INSERT INTO caught_balls (user_id, url, name, timestamp, shiny_status) VALUES (?, ?, ?, ?, ?)",
                   (user_id, url, name, timestamp, shiny_status))
    conn.commit()

def get_caught_balls_for_user(user_id):
    cursor.execute("SELECT url, name, timestamp FROM caught_balls WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    return rows

def read_config_file():
    config = {}
    if os.path.exists("config.txt"):
        with open("config.txt", "r") as file:
            lines = file.readlines()
            for line in lines:
                channel_id, server_id = line.strip().split(':')
                config[int(server_id)] = int(channel_id)
    return config

configured_channels = read_config_file()

@bot.event
async def on_ready():
    print(f"{time.ctime()} | Logged in as {bot.user.name} ({bot.user.id})")
    print(f"{time.ctime()} | Prefix: {prefix}")
    print(f"{time.ctime()} | Servers: {len(bot.guilds)}")
    print(f"{time.ctime()} | Commands loaded: {len(bot.commands)}")
    await bot.change_presence(status=discord.Status.online, activity=discord.Game("FBI | /help"))

    spawn_ball.start()

@tree.command(name=f"{slash_command_name}_list", description=f"List your {collectibles_name}.")
async def list_collectibles(interaction: discord.Interaction):
    caught_balls = get_caught_balls_for_user(interaction.user.id)
    if caught_balls:
        embed = discord.Embed(
            title=f"Your {collectibles_name.capitalize()}",
            description="Here is what you own:",
            color=discord.Color.blue()
        )
        for url, name, timestamp in caught_balls:
            embed.add_field(name=name.capitalize(), value=f"Caught at: <t:{int(timestamp)}:F>", inline=False)
    else:
        embed = discord.Embed(
            title=f"No {collectibles_name.capitalize()} Found",
            description=f"You haven't caught any {collectibles_name} yet!",
            color=discord.Color.red()
        )
    await interaction.response.send_message(embed=embed)
    
@tree.command(name=f"{slash_command_name}_completion", description=f"Show your current completion of {bot_name}.")
async def completion(interaction: discord.Interaction, member: discord.Member = None):
    if member is None:
        member = interaction.user

    username = member.display_name
    user_id = member.id

    owned_balls = get_caught_balls_for_user(user_id)
    user_owned_balls = {ball[1]: ball[0] for ball in owned_balls}

    all_balls_data = countryballs.items()

    with open('emojis.json', 'r') as emojis_file:
        ball_to_emoji = json.load(emojis_file).get("ball_to_emoji", {})

    embed = discord.Embed(
        title=f"{username}'s",
        description=f"{bot_name} progression: **{len(user_owned_balls)/len(all_balls_data)*100:.2f}%**",
        color=discord.Color.blurple(),
    ).set_thumbnail(url=member.avatar.url)

    if user_owned_balls:
        owned_list = ' '.join([ball_to_emoji.get(name, '') or name.capitalize() for name in user_owned_balls.keys()])
        embed.add_field(name=f"Owned {collectibles_name.capitalize()}", value=owned_list, inline=False)
    else:
        embed.add_field(name=f"Owned {collectibles_name.capitalize()}", value=f"No owned {collectibles_name} yet.", inline=False)

    missing_balls = [(name, url) for name, url in all_balls_data if name not in user_owned_balls]

    if missing_balls:
        missing_list = ' '.join([ball_to_emoji.get(name, '') or f"[{name.capitalize()}]({url})" for name, url in missing_balls])
        embed.add_field(name=f"Missing {collectibles_name.capitalize()}", value=missing_list, inline=False)
    else:
        embed.add_field(name=f"Missing {collectibles_name.capitalize()}", value=f"", inline=False)

    await interaction.response.send_message(embed=embed)

@bot.command()
@commands.guild_only()
@commands.is_owner()
async def reloadtree(ctx: commands.Context, guilds: commands.Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
    if not guilds:
        if spec == "~":
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "*":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "^":
            ctx.bot.tree.clear_commands(guild=ctx.guild)
            await ctx.bot.tree.sync(guild=ctx.guild)
            synced = []
        else:
            synced = await ctx.bot.tree.sync()

        await ctx.send(
            f"Synced {len(synced)} tree {'globally' if spec is None else 'to the current guild.'}"
        )
        return

    ret = 0
    for guild in guilds:
        try:
            await ctx.bot.tree.sync(guild=guild)
        except discord.HTTPException:
            pass
        else:
            ret += 1

    await ctx.send(f"Synced the tree to {ret}/{len(guilds)}")

@tree.command(name="ping", description="Ping the bot.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong! {}ms".format(round(bot.latency * 1000)))

@bot.command()
@commands.is_owner()
async def kill(ctx):
    await ctx.send("dying!! :sob:")
    await bot.close()

@bot.command()
@commands.is_owner()
async def giveball(ctx, user: discord.User, url: str, shiny_status: Optional[str] = "No"):
    ballname = url.split('/')[-1].split('.')[0]
    timestamp = time.time()
    add_caught_ball(user.id, url, ballname, timestamp, shiny_status)
    await ctx.send(f"The \"{ballname}\" {collectibles_name} was given to {user.display_name}.")

class CatchModal(discord.ui.Modal):
    def __init__(self, countryball_name, countryball_url, catch_button):
        super().__init__(title=f'Catch the {collectibles_name}!')
        self.correct_name = countryball_name
        self.countryball_url = countryball_url
        self.catch_button = catch_button
        self.countryball_name_input = discord.ui.TextInput(
            label=f'Name this {collectibles_name}!',
            style=discord.TextStyle.short,
            placeholder=f'What is the name of this {collectibles_name}',
            required=True
        )
        self.add_item(self.countryball_name_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.catch_button.disabled:
            await interaction.response.send_message("This countryball has already been caught!", ephemeral=True)
            return

        if self.countryball_name_input.value.lower() == self.correct_name.lower():
            add_caught_ball(interaction.user.id, self.countryball_url, self.correct_name, time.time(), "No")
            await interaction.response.send_message(f"{interaction.user.mention} You caught **{self.correct_name}!**", ephemeral=False)
            self.catch_button.disabled = True
            self.catch_button.label = "Caught!"
            await interaction.message.edit(view=self.catch_button.view)
        else:
            await interaction.response.send_message(f"{interaction.user.mention} Wrong name!", ephemeral=True)

@tasks.loop(hours=2)
async def spawn_ball():
    for server_id, channel_id in configured_channels.items():
        channel = bot.get_channel(channel_id)
        if channel:
            countryball_choice = random.choice(list(countryballs.items()))
            random_countryball_name, random_countryball_url = countryball_choice

            embed = discord.Embed(
                title=f"A wild {collectibles_name} appeared!"
            )
            embed.set_image(url=random_countryball_url)

            view = discord.ui.View()
            catch_button = discord.ui.Button(label="Catch me!", style=discord.ButtonStyle.primary)
            def catch_button_callback(interaction, name=random_countryball_name, url=random_countryball_url, button=catch_button):
                bot.loop.create_task(
                    interaction.response.send_modal(
                        CatchModal(name, url, button)
                    )
                )
            catch_button.callback = catch_button_callback
            view.add_item(catch_button)

            try:
                message = await channel.send(embed=embed, view=view)
                caught_balls[message.id] = {
                    'url': random_countryball_url,
                    'name': random_countryball_name,
                    'timestamp': time.time(),
                    'channel_id': channel_id
                }
            except discord.HTTPException as e:
                print(f"Failed to send message in channel {channel_id}: {e}")

            await asyncio.sleep(10)
        else:
            print(f"Channel with ID {channel_id} not found or bot doesn't have access.")

bot.run(token)
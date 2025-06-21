import os
import asyncio
import discord
import asyncpg  # Ajout pour la commande /scores

from src.log import logger

from g4f.client import Client
from g4f.Provider import (RetryProvider, FreeGpt, ChatgptNext, AItianhuSpace,
                        You, OpenaiChat, FreeChatgpt, Liaobots,
                        Gemini, Bing)

from src.aclient import discordClient
from discord import app_commands
from src import log, art, personas
from src.db.db_commands import DatabaseCommands

# Initialize a flag to skip the first loop iteration
skip_first_loop = False

# Informations sur la dernière mise à jour
LAST_UPDATE_DATE = "2025-05-31"
LAST_UPDATE_SUMMARY = (
    "- Ajout de la commande /lastupdate et intégration dans /help\n"
    "- Génération dynamique des choix de personnalités à partir de personas.py\n"
    "- Correction du changement de personnalité\n"
    "- Ajout automatique de la description lors de la création de nouvelles personnalités\n"
    "- Ajout de la commande /scores pour afficher le classement\n"
    "- Ajout de la commande /quiz pour répondre à l'énigme du jour (+10 points si bonne réponse dans l'heure)\n"
    "- Ajout de la commande /vote pour lancer un vote à choix multiples avec résultats automatiques\n"
)

def run_discord_bot():
    # Instanciation du client Discord AVANT la déclaration des events/commandes
    client = discordClient()

    @client.event
    async def on_ready():
        global skip_first_loop
        await client.tree.sync()
        # Création des bases pour tous les serveurs déjà présents
        for guild in client.guilds:
            logger.info(f"[DB] Initialisation de la base pour le serveur {guild.name} ({guild.id})")
            await client.create_database_for_guild(guild)
            # Lancer le quiz quotidien (une seule fois par jour)
            client.start_daily_quiz_task(guild)
        await client.send_start_prompt()
        loop = asyncio.get_event_loop()
        loop.create_task(client.process_messages())
        logger.info(f'{client.user} est connecté!')


    @client.event
    async def on_guild_join(guild):
        logger.info(f"Nouveau serveur rejoint : {guild.name} ({guild.id})")
        logger.info(f"[DB] Initialisation de la base pour le serveur {guild.name} ({guild.id})")
        await client.create_database_for_guild(guild)


    @client.tree.command(name="chat", description="Discute avec moi")
    async def chat(interaction: discord.Interaction, *, message: str):
        if client.is_replying_all == "True":
            await interaction.response.defer(ephemeral=False)
            await interaction.followup.send(
                "> **WARN: You already on replyAll mode. If you want to use the Slash Command, switch to normal mode by using `/replyall` again**")
            logger.warning("\x1b[31mYou already on replyAll mode, can't use slash command!\x1b[0m")
            return
        if interaction.user == client.user:
            return
        username = str(interaction.user)
        client.current_channel = interaction.channel
        logger.info(
            f"\x1b[31m{username}\x1b[0m : /chat [{message}] in ({client.current_channel})")

        await client.enqueue_message(interaction, message)


    @client.tree.command(name="private", description="Toggle private access")
    async def private(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        if not client.isPrivate:
            client.isPrivate = not client.isPrivate
            logger.warning("\x1b[31mSwitch to private mode\x1b[0m")
            await interaction.followup.send(
                "> **INFO: Next, the response will be sent via private reply. If you want to switch back to public mode, use `/public`**")
        else:
            logger.info("You already on private mode!")
            await interaction.followup.send(
                "> **WARN: You already on private mode. If you want to switch to public mode, use `/public`**")


    @client.tree.command(name="public", description="Toggle public access")
    async def public(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        if client.isPrivate:
            client.isPrivate = not client.isPrivate
            await interaction.followup.send(
                "> **INFO: Next, the response will be sent to the channel directly. If you want to switch back to private mode, use `/private`**")
            logger.warning("\x1b[31mSwitch to public mode\x1b[0m")
        else:
            await interaction.followup.send(
                "> **WARN: You already on public mode. If you want to switch to private mode, use `/private`**")
            logger.info("You already on public mode!")


    @client.tree.command(name="replyall", description="Toggle replyAll access")
    async def replyall(interaction: discord.Interaction):
        client.replying_all_discord_channel_id = str(interaction.channel_id)
        await interaction.response.defer(ephemeral=False)
        if client.is_replying_all == "True":
            client.is_replying_all = "False"
            await interaction.followup.send(
                "> **INFO: Next, the bot will response to the Slash Command. If you want to switch back to replyAll mode, use `/replyAll` again**")
            logger.warning("\x1b[31mSwitch to normal mode\x1b[0m")
        elif client.is_replying_all == "False":
            client.is_replying_all = "True"
            await interaction.followup.send(
                "> **INFO: Next, the bot will disable Slash Command and responding to all message in this channel only. If you want to switch back to normal mode, use `/replyAll` again**")
            logger.warning("\x1b[31mSwitch to replyAll mode\x1b[0m")


    # @discordClient.tree.command(name="chat-model", description="Change de modèle entre 'gemini' et 'gpt-4'")
    # @app_commands.choices(model=[
    #     app_commands.Choice(name="gemini", value="gemini"),
    #     app_commands.Choice(name="gpt-4", value="gpt-4"),
    #     app_commands.Choice(name="gpt-3.5-turbo", value="gpt-3.5-turbo"),
    # ])
    # async def chat_model(interaction: discord.Interaction, model: app_commands.Choice[str]):
    #     await interaction.response.defer(ephemeral=True)
    #     try:
    #         if model.value == "gemini":
    #             discordClient.reset_conversation_history()
    #             discordClient.chatBot = Client(provider=RetryProvider([Gemini, FreeChatgpt], shuffle=False))
    #             discordClient.chatModel = model.value
    #         elif model.value == "gpt-4":
    #             discordClient.reset_conversation_history()
    #             discordClient.chatBot = Client(provider=RetryProvider([Liaobots, You, OpenaiChat, Bing], shuffle=False))
    #             discordClient.chatModel = model.value
    #         elif model.value == "gpt-3.5-turbo":
    #             discordClient.reset_conversation_history()
    #             discordClient.chatBot = Client(provider=RetryProvider([FreeGpt, ChatgptNext, AItianhuSpace], shuffle=False))
    #             discordClient.chatModel = model.value

    #         await interaction.followup.send(f"> **INFO: Chat model switched to {model.name}.**")
    #         logger.info(f"Switched chat model to {model.name}")

    #     except Exception as e:
    #         await interaction.followup.send(f'> **Error Switching Model: {e}**')
    #         logger.error(f"Error switching chat model: {e}")

    @client.tree.command(name="reset", description="Reset la discussion")
    async def reset(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        client.conversation_history = []
        await interaction.followup.send("> **INFO: J'ai tout oublié.**")
        personas.current_persona = "standard"
        logger.warning(
            f"\x1b[31m{discordClient.chatModel} bot has been successfully reset\x1b[0m")

    @client.tree.command(name="lastupdate", description="Affiche la date et le contenu de la dernière mise à jour du bot")
    async def lastupdate(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            f"**Dernière mise à jour :** {LAST_UPDATE_DATE}\n"
            f"**Changements :**\n{LAST_UPDATE_SUMMARY}"
        )

    @client.tree.command(name="help", description="Montre les commandes du bot")
    async def help(interaction: discord.Interaction):
        help_text = (
            "**Commandes disponibles :**\n"
            "/chat [message] : Discute avec Madame Kirma\n"
            "/private : Passe en mode réponse privée\n"
            "/public : Passe en mode réponse publique\n"
            "/replyall : Active/désactive le mode réponse à tous les messages\n"
            "/reset : Réinitialise la discussion\n"
            "/switchpersona : Change la personnalité de Madame Kirma\n"
            "/createpersona : Ajoute une personnalité custom\n"
            "/currentpersona : Affiche la personnalité active\n"
            "/scores : Affiche le classement des scores du serveur\n"
            "/quiz [réponse] : Réponds à l'énigme du jour (1h pour répondre, +10 points si bonne réponse)\n"
            "/vote [question] [choix1] [choix2] ... : Lance un vote avec 2 à 5 choix, résultats après 1 min\n"
            "/draw [prompt] [model] : Génère une image avec Dall-e, Gemini ou Bing\n"
            "/lastupdate : Affiche la date et le contenu de la dernière mise à jour du bot\n"
            "\n**Fonctionnalités récentes :**\n"
            f"{LAST_UPDATE_SUMMARY}"
        )
        await interaction.response.send_message(help_text, ephemeral=True)
        logger.info(
            "\x1b[31mSomeone needs help!\x1b[0m")


    @client.tree.command(name="draw", description="Generate an image with the Dall-e-3 model")
    @app_commands.choices(model=[
        app_commands.Choice(name="gemini", value="gemini"),
        app_commands.Choice(name="openai", value="openai"),
        app_commands.Choice(name="bing", value="BingCreateImages"),
    ])
    async def draw(interaction: discord.Interaction, *, prompt: str, model: app_commands.Choice[str]):
        if interaction.user == client.user:
            return

        username = str(interaction.user)
        channel = str(interaction.channel)
        logger.info(
            f"\x1b[31m{username}\x1b[0m : /draw [{prompt}] in ({channel})")

        await interaction.response.defer(thinking=True, ephemeral=client.isPrivate)
        try:
            image_url = await art.draw(model.value, prompt)

            await interaction.followup.send(image_url)

        except Exception as e:
            await interaction.followup.send(
                f'> Something Went Wrong, try again later.\n\nError Message:{e}')
            logger.info(f"\x1b[31m{username}\x1b[0m :{e}")

    # Générer dynamiquement les choix pour les personas à partir de personas.PERSONAS
    all_personas = [
        app_commands.Choice(
            name=f"{key.capitalize()} : {value['description'][:50]}...",
            value=key
        )
        for key, value in personas.PERSONAS.items()
    ]

    @client.tree.command(
        name="switchpersona",
        description="Changer entre les personnalités de Madame Kirma"
    )
    @app_commands.describe(persona="Choisissez une personnalité parmi la liste")
    @app_commands.choices(persona=all_personas)
    async def switchpersona(interaction: discord.Interaction, persona: app_commands.Choice[str]):
        # On récupère la valeur réelle du choix
        persona_value = persona.value if isinstance(persona, app_commands.Choice) else persona

        # Vérifier si la persona existe
        if persona_value not in personas.PERSONAS:
            await interaction.response.send_message(
                f"> **ERREUR : La personnalité `{persona_value}` n'est pas disponible. 😿**", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            # Correction : passe uniquement persona_value
            await client.switch_persona(persona_value)
            personas.current_persona = persona_value
            await interaction.followup.send(
                f"> **INFO : Personnalité changée en `{persona_value}` avec succès.**\nDescription : {personas.PERSONAS[persona_value]['description']}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(
                "> **ERREUR : Une erreur est survenue, veuillez réessayer plus tard.**", ephemeral=True)
            logger.exception(f"Erreur lors du changement de personnalité : {e}")


    @client.tree.command(name="createpersona", description="Ajouter une personnalité custom")
    async def createPersona(interaction: discord.Interaction, name: str, description: str, prompt: str):
        if interaction.user == client.user:
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        username = str(interaction.user)
        logger.info(
            f"\x1b[31m{username}\x1b[0m : '/createpersona [{name}] - [{description}]'"
        )

        if name in personas.PERSONAS:
            await interaction.followup.send(
                f"> **ERREUR : Une personnalité avec le nom `{name}` existe déjà.**", ephemeral=True)
            logger.warning(f"Personality `{name}` already exists.")
        else:
            try:
                # Add the new persona to the personas module (respect structure)
                with open("src/personas.py", "a", encoding="utf-8") as f:
                    f.write(f'\nPERSONAS["{name}"] = {{"description": """{description}""", "prompt": """{prompt}"""}}\n')

                personas.PERSONAS[name] = {"description": description, "prompt": prompt}
                personas.current_persona = name
                await client.switch_persona(name)
                await interaction.followup.send(
                    f"> **INFO : Personnalité `{name}` ajoutée et activée avec succès !**\nDescription : {description}", ephemeral=True)
                logger.info(f"Custom persona `{name}` added and activated successfully.")
            except Exception as e:
                await interaction.followup.send(
                    "> **ERREUR : Une erreur est survenue lors de l'ajout de la personnalité.**", ephemeral=True)
                logger.exception(f"Erreur lors de l'ajout de la personnalité `{name}` : {e}")

    # @discordClient.tree.command(name="clearchannel", description="Efface tous les messages du canal courant (si permissions)")
    # async def clearchannel(interaction: discord.Interaction):
    #     await interaction.response.defer(ephemeral=True)
    #     channel = interaction.channel
    #     try:
    #         deleted = await channel.purge(limit=100)
    #         await interaction.followup.send(f"> **INFO : {len(deleted)} messages ont été supprimés dans ce canal.**")
    #     except Exception as e:
    #         await interaction.followup.send("> **ERREUR : Impossible de supprimer les messages (permissions manquantes ?).**")
    #         logger.exception(f"Erreur lors de la suppression des messages : {e}")

    # @discordClient.tree.command(DatabaseCommands(name="db", description='Access to database functionalities'))

    @client.event
    async def on_message(message):
        if client.is_replying_all == "True":
            if message.author == client.user:
                return
            if client.replying_all_discord_channel_id:
                if message.channel.id == int(client.replying_all_discord_channel_id):
                    username = str(message.author)
                    user_message = str(message.content)
                    client.current_channel = message.channel
                    logger.info(f"\x1b[31m{username}\x1b[0m : '{user_message}' ({client.current_channel})")
                    await client.enqueue_message(message, user_message)
            else:
                logger.exception("replying_all_discord_channel_id not found, please use the command `/replyall` again.")

    @client.tree.command(name="currentpersona", description="Affiche la personnalité actuellement active")
    async def currentpersona(interaction: discord.Interaction):
        persona = personas.current_persona
        desc = personas.PERSONAS.get(persona, {}).get("description", "Aucune description disponible.")
        await interaction.response.send_message(
            f"> **Personnalité actuelle :** `{persona}`\nDescription : {desc}", ephemeral=True
        )

    @client.tree.command(name="scores", description="Affiche le classement des scores du serveur")
    async def scores(interaction: discord.Interaction):
        guild = interaction.guild
        db_user = os.getenv('PGUSER')
        db_password = os.getenv('PGPASSWORD')
        db_host = os.getenv('PGHOST', 'localhost')
        db_port = os.getenv('PGPORT', '5432')
        db_name = f"guild_{guild.id}"
        try:
            conn = await asyncpg.connect(user=db_user, password=db_password, database=db_name, host=db_host, port=db_port)
            rows = await conn.fetch("SELECT username, score FROM Users ORDER BY score DESC, username ASC LIMIT 5;")
            await conn.close()
            if not rows:
                await interaction.response.send_message("> Aucun score à afficher pour ce serveur.", ephemeral=True)
                return
            classement = "\n".join([f"**{i+1}.** {r['username']} : {r['score']} pts" for i, r in enumerate(rows)])
            await interaction.response.send_message(f"**Classement des scores :**\n{classement}", ephemeral=False)
        except Exception as e:
            await interaction.response.send_message("> Erreur lors de la récupération des scores.", ephemeral=True)
            logger.exception(f"Erreur lors de l'affichage des scores : {e}")

    @client.tree.command(name="quiz", description="Réponds à l'énigme du jour !")
    async def quiz(interaction: discord.Interaction, *, reponse: str):
        user_id = interaction.user.id
        username = str(interaction.user)
        guild = interaction.guild
        result, message = await client.check_quiz_answer(guild, user_id, username, reponse)
        await interaction.response.send_message(message, ephemeral=True)

    @client.tree.command(name="vote", description="Lance un vote avec jusqu'à 5 choix. Résultats après 5 minutes.")
    @app_commands.describe(question="La question du vote", choix1="Premier choix", choix2="Deuxième choix", choix3="Troisième choix", choix4="Quatrième choix", choix5="Cinquième choix")
    async def vote(
        interaction: discord.Interaction,
        question: str,
        choix1: str,
        choix2: str = None,
        choix3: str = None,
        choix4: str = None,
        choix5: str = None
    ):
        await interaction.response.defer(ephemeral=False)
        choix_list = [c for c in [choix1, choix2, choix3, choix4, choix5] if c]
        if len(choix_list) < 2:
            await interaction.followup.send("> **ERREUR : Il faut au moins 2 choix pour lancer un vote.**", ephemeral=True)
            return
        emojis = ["🇦", "🇧", "🇨", "🇩", "🇪"]
        description = "\n".join([f"{emojis[i]} {choix_list[i]}" for i in range(len(choix_list))])
        embed = discord.Embed(title=f"📊 {question}", description=description, color=0x5865F2)
        vote_message = await interaction.followup.send(embed=embed, wait=True)
        for i in range(len(choix_list)):
            await vote_message.add_reaction(emojis[i])
        await asyncio.sleep(60*5)  # 5 minute de vote
        vote_message = await interaction.channel.fetch_message(vote_message.id)
        results = []
        for i, emoji in enumerate(emojis[:len(choix_list)]):
            count = 0
            for reaction in vote_message.reactions:
                if str(reaction.emoji) == emoji:
                    count = reaction.count - 1  # On retire le bot
            results.append(f"{emoji} {choix_list[i]} : {count} vote(s)")
        result_text = "\n".join(results)
        await interaction.followup.send(f"**Résultats du vote :**\n{result_text}")

    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    client.run(TOKEN)

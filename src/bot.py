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
LAST_UPDATE_DATE = "2025-07-07"
LAST_UPDATE_SUMMARY = (
    "- Ajout de la commande /lastupdate\n"
    "- Ajout de la commande /currentpersona pour afficher la personnalité active\n"
    "- Ajout de la commande /scores pour afficher le classement du serveur\n"
    "- Ajout de la commande /vote pour lancer des votes à choix multiples (résultats après 5 min)\n"
    "- Ajout de la commande /createpersona pour créer des personnalités custom\n"
    "- Amélioration du système de quiz avec correspondance floue et cache des réponses\n"
    "- Ajout des fonctionnalités de recherche web avec OpenAI\n"
    "- Système de quiz automatique avec 2 énigmes par jour (matin et après-midi)\n"
)

def run_discord_bot():            

    @discordClient.event
    async def on_ready():
        global skip_first_loop
        await discordClient.send_start_prompt()
        await discordClient.tree.sync()
        loop = asyncio.get_event_loop()
        loop.create_task(discordClient.process_messages())
        logger.info(f'{discordClient.user} est connecté!')


    @discordClient.tree.command(name="websearch", description="Chat with web search capabilities")
    async def websearch(interaction: discord.Interaction, *, message: str):
        if discordClient.is_replying_all == "True":
            await interaction.response.defer(ephemeral=False)
            await interaction.followup.send(
                "> **WARN: You already on replyAll mode. If you want to use the Slash Command, switch to normal mode by using `/replyall` again**")
            logger.warning("\x1b[31mYou already on replyAll mode, can't use slash command!\x1b[0m")
            return
        if interaction.user == discordClient.user:
            return

        # Check if OpenAI is enabled for web search
        if os.getenv("OPENAI_ENABLED") == "False":
            await interaction.response.defer(ephemeral=False)
            await interaction.followup.send(
                "> **ERROR: Web search requires OpenAI to be enabled. Please set OPENAI_ENABLED=True in your environment variables.**")
            logger.error("Web search attempted but OpenAI is disabled")
            return

        username = str(interaction.user)
        discordClient.current_channel = interaction.channel
        logger.info(
            f"\x1b[31m{username}\x1b[0m : /websearch [{message}] in ({discordClient.current_channel})")

        await discordClient.enqueue_web_search_message(interaction, message, already_deferred=True)


    @discordClient.tree.command(name="chat", description="Discute avec moi")
    async def chat(interaction: discord.Interaction, *, message: str):
        if discordClient.is_replying_all == "True":
            await interaction.response.defer(ephemeral=False)
            await interaction.followup.send(
                "> **WARN: You already on replyAll mode. If you want to use the Slash Command, switch to normal mode by using `/replyall` again**")
            logger.warning("\x1b[31mYou already on replyAll mode, can't use slash command!\x1b[0m")
            return
        if interaction.user == discordClient.user:
            return
        username = str(interaction.user)
        discordClient.current_channel = interaction.channel
        logger.info(
            f"\x1b[31m{username}\x1b[0m : /chat [{message}] in ({discordClient.current_channel})")

        # Check if web search mode is enabled and use appropriate method
        if discordClient.web_search_mode and os.getenv("OPENAI_ENABLED") == "True":
            await discordClient.enqueue_web_search_message(interaction, message, already_deferred=True)
        else:
            await discordClient.enqueue_message(interaction, message)


    @discordClient.tree.command(name="private", description="Toggle private access")
    async def private(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        if not discordClient.isPrivate:
            discordClient.isPrivate = not discordClient.isPrivate
            logger.warning("\x1b[31mSwitch to private mode\x1b[0m")
            await interaction.followup.send(
                "> **INFO: Next, the response will be sent via private reply. If you want to switch back to public mode, use `/public`**")
        else:
            logger.info("You already on private mode!")
            await interaction.followup.send(
                "> **WARN: You already on private mode. If you want to switch to public mode, use `/public`**")


    @discordClient.tree.command(name="public", description="Toggle public access")
    async def public(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        if discordClient.isPrivate:
            discordClient.isPrivate = not discordClient.isPrivate
            await interaction.followup.send(
                "> **INFO: Next, the response will be sent to the channel directly. If you want to switch back to private mode, use `/private`**")
            logger.warning("\x1b[31mSwitch to public mode\x1b[0m")
        else:
            await interaction.followup.send(
                "> **WARN: You already on public mode. If you want to switch to private mode, use `/private`**")
            logger.info("You already on public mode!")


    @discordClient.tree.command(name="togglewebsearch", description="Toggle web search mode for all chat commands")
    async def togglewebsearch(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        # Check if OpenAI is enabled
        if os.getenv("OPENAI_ENABLED") == "False":
            await interaction.followup.send(
                "> **ERROR: Web search requires OpenAI to be enabled. Please set OPENAI_ENABLED=True in your environment variables.**")
            logger.error("Web search toggle attempted but OpenAI is disabled")
            return

        discordClient.web_search_mode = not discordClient.web_search_mode

        if discordClient.web_search_mode:
            await interaction.followup.send(
                "> **INFO: Web search mode enabled. All chat commands (/chat and replyall) will now use web search capabilities.**")
            logger.info("Web search mode enabled for all chat commands")
        else:
            await interaction.followup.send(
                "> **INFO: Web search mode disabled. Chat commands will use standard chat without web search.**")
            logger.info("Web search mode disabled for all chat commands")


    @discordClient.tree.command(name="replyall", description="Toggle replyAll access")
    async def replyall(interaction: discord.Interaction):
        discordClient.replying_all_discord_channel_id = str(interaction.channel_id)
        await interaction.response.defer(ephemeral=False)
        if discordClient.is_replying_all == "True":
            discordClient.is_replying_all = "False"
            await interaction.followup.send(
                "> **INFO: Next, the bot will response to the Slash Command. If you want to switch back to replyAll mode, use `/replyAll` again**")
            logger.warning("\x1b[31mSwitch to normal mode\x1b[0m")
        elif discordClient.is_replying_all == "False":
            discordClient.is_replying_all = "True"
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

    @discordClient.tree.command(name="reset", description="Reset la discussion")
    async def reset(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        discordClient.conversation_history = []
        await interaction.followup.send("> **INFO: J'ai tout oublié.**")
        personas.current_persona = "standard"
        logger.warning(
            f"\x1b[31m{discordClient.chatModel} bot has been successfully reset\x1b[0m")

    @discordClient.tree.command(name="lastupdate", description="Affiche la date et le contenu de la dernière mise à jour du bot")
    async def lastupdate(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            f"**Dernière mise à jour :** {LAST_UPDATE_DATE}\n"
            f"**Changements :**\n{LAST_UPDATE_SUMMARY}"
        )

    @discordClient.tree.command(name="quiz", description="Répondre à l'énigme du jour")
    async def quiz(interaction: discord.Interaction, *, reponse: str):
        if interaction.user == discordClient.user:
            return

        await interaction.response.defer(ephemeral=False)
        username = str(interaction.user)
        user_id = interaction.user.id
        guild = interaction.guild
        
        logger.info(f"\x1b[31m{username}\x1b[0m : /quiz [{reponse}] in ({guild.name if guild else 'DM'})")

        if not guild:
            await interaction.followup.send("> **ERREUR: Les quiz ne sont disponibles que dans les serveurs.**")
            return

        try:
            is_correct, message = await discordClient.check_quiz_answer(guild, user_id, username, reponse)
            
            if is_correct:
                await interaction.followup.send(f"> ✅ {message}")
            else:
                await interaction.followup.send(f"> ❌ {message}")
                
        except Exception as e:
            await interaction.followup.send("> **ERREUR: Une erreur est survenue, veuillez réessayer plus tard.**")
            logger.exception(f"Erreur lors de la vérification de la réponse au quiz : {e}")

    @discordClient.tree.command(name="help", description="Montre les commandes du bot")
    async def help(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        await interaction.followup.send(""":crystal_ball: **COMMANDES BASIQUES** :crystal_ball:
- `/chat [message]` Dis moi ce que tu veux savoir - respecte le toggle de recherche web.
- `/websearch [message]` Chat avec capacités de recherche web (nécessite OpenAI).
- `/draw [prompt][model]` Je peux générer une image avec un modèle spécifique.
- `/quiz [réponse]` Réponds à l'énigme du jour ! 2 énigmes par jour (matin et après-midi).
- `/switchpersona [persona]` Change la personnalité de Madame Kirma
- `/currentpersona` Affiche la personnalité actuellement active.
- `/createpersona [nom][description][prompt]` Créer une personnalité custom.
- `/scores` Affiche le classement des scores du serveur.
- `/vote [question][choix1][choix2]...` Lance un vote à choix multiples (résultats après 5 min).
- `/lastupdate` Affiche les informations sur la dernière mise à jour du bot.
- `/private` Je passe en mode privé (coquinou).
- `/public` Je passe en mode public.
- `/replyall` Bascule entre le mode replyAll et le mode par défaut.
- `/togglewebsearch` Active/désactive le mode recherche web pour toutes les commandes chat (nécessite OpenAI).
- `/reset` Réinitialise l'historique de la conversation.                        
""")

        logger.info(
            "\x1b[31mSomeone needs help!\x1b[0m")


    @discordClient.tree.command(name="draw", description="Generate an image with the Dall-e-3 model")
    @app_commands.choices(model=[
        app_commands.Choice(name="gemini", value="gemini"),
        app_commands.Choice(name="openai", value="openai"),
        app_commands.Choice(name="bing", value="BingCreateImages"),
    ])
    async def draw(interaction: discord.Interaction, *, prompt: str, model: app_commands.Choice[str]):
        if interaction.user == discordClient.user:
            return

        username = str(interaction.user)
        channel = str(interaction.channel)
        logger.info(
            f"\x1b[31m{username}\x1b[0m : /draw [{prompt}] in ({channel})")

        await interaction.response.defer(thinking=True, ephemeral=discordClient.isPrivate)
        try:
            image_url = await art.draw(model.value, prompt)

            await interaction.followup.send(image_url)

        except Exception as e:
            await interaction.followup.send(
                f'> Something Went Wrong, try again later.\n\nError Message:{e}')
            logger.info(f"\x1b[31m{username}\x1b[0m :{e}")

    @discordClient.tree.command(name="switchpersona", description="Changer entre les personnalités de Madame Kirma")
    @app_commands.choices(persona=[
        app_commands.Choice(name="Standard", value="standard"),
        app_commands.Choice(name="Lundi : Furieuse et arrogante", value="mon"),
        app_commands.Choice(name="Mardi : Intellectuelle prétentieuse", value="tue"),
        app_commands.Choice(name="Mercredi : Hippie perchée", value="wed"),
        app_commands.Choice(name="Jeudi : Séductrice exubérante", value="thu"),
        app_commands.Choice(name="Vendredi : Fêtarde surexcitée", value="fri"),
        app_commands.Choice(name="Samedi : Épuisée d'après-soirée", value="sat"),
        app_commands.Choice(name="Dimanche : Blasée du lundi", value="sun"),
    ])
    async def switchpersona(interaction: discord.Interaction, persona: app_commands.Choice[str]):
        if interaction.user == discordClient.user:
            return

        await interaction.response.defer(thinking=True)
        username = str(interaction.user)
        channel = str(interaction.channel)
        logger.info(
            f"\x1b[31m{username}\x1b[0m : '/switchpersona [{persona.value}]' ({channel})"
        )

        persona = persona.value

        if persona == personas.current_persona:
            await interaction.followup.send(
                f"> **ATTENTION : La personnalité `{persona}` est déjà active.**")
        elif persona in personas.PERSONAS:
            try:
                await discordClient.switch_persona(persona)
                personas.current_persona = persona
                await interaction.followup.send(
                    f"> **INFO : Personnalité changée en `{persona}` avec succès.**")
            except Exception as e:
                await interaction.followup.send(
                    "> **ERREUR : Une erreur est survenue, veuillez réessayer plus tard.**")
                logger.exception(f"Erreur lors du changement de personnalité : {e}")
        else:
            await interaction.followup.send(
                f"> **ERREUR : La personnalité `{persona}` n'est pas disponible. 😿**")
            logger.info(
                f'{username} a demandé une personnalité indisponible : `{persona}`')

    # @discordClient.tree.command(DatabaseCommands(name="db", description='Access to database functionalities'))

    @discordClient.tree.command(name="currentpersona", description="Affiche la personnalité actuellement active")
    async def currentpersona(interaction: discord.Interaction):
        persona = personas.current_persona
        desc = personas.PERSONAS.get(persona, {}).get("description", "Aucune description disponible.")
        await interaction.response.send_message(
            f"> **Personnalité actuelle :** `{persona}`\nDescription : {desc}", ephemeral=True
        )

    @discordClient.tree.command(name="scores", description="Affiche le classement des scores du serveur")
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
                await interaction.followup.send("> Aucun score à afficher pour ce serveur.", ephemeral=True)
                return
            classement = "\n".join([f"**{i+1}.** {r['username']} : {r['score']} pts" for i, r in enumerate(rows)])
            await interaction.followup.send(f"**Classement des scores :**\n{classement}", ephemeral=False)
        except Exception as e:
            await interaction.followup.send("> Erreur lors de la récupération des scores.", ephemeral=True)
            logger.exception(f"Erreur lors de l'affichage des scores : {e}")

    @discordClient.tree.command(name="vote", description="Lance un vote avec jusqu'à 5 choix. Résultats après 5 minutes.")
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
        await asyncio.sleep(60*5)  # 5 minutes de vote
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

    @discordClient.tree.command(name="createpersona", description="Ajouter une personnalité custom")
    async def createPersona(interaction: discord.Interaction, name: str, description: str, prompt: str):
        if interaction.user == discordClient.user:
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
                await discordClient.switch_persona(name)
                await interaction.followup.send(
                    f"> **INFO : Personnalité `{name}` ajoutée et activée avec succès !**\nDescription : {description}", ephemeral=True)
                logger.info(f"Custom persona `{name}` added and activated successfully.")
            except Exception as e:
                await interaction.followup.send(
                    "> **ERREUR : Une erreur est survenue lors de l'ajout de la personnalité.**", ephemeral=True)
                logger.exception(f"Erreur lors de l'ajout de la personnalité `{name}` : {e}")

    @discordClient.event
    async def on_message(message):
        if discordClient.is_replying_all == "True":
            if message.author == discordClient.user:
                return
            if discordClient.replying_all_discord_channel_id:
                if message.channel.id == int(discordClient.replying_all_discord_channel_id):
                    username = str(message.author)
                    user_message = str(message.content)
                    discordClient.current_channel = message.channel
                    logger.info(f"\x1b[31m{username}\x1b[0m : '{user_message}' ({discordClient.current_channel})")

                    # Use web search if enabled and OpenAI is available
                    if discordClient.web_search_mode and os.getenv("OPENAI_ENABLED") == "True":
                        await discordClient.enqueue_web_search_message(message, user_message)
                    else:
                        await discordClient.enqueue_message(message, user_message)
            else:
                logger.exception("replying_all_discord_channel_id not found, please use the command `/replyall` again.")

    TOKEN = os.getenv("DISCORD_BOT_TOKEN")

    discordClient.run(TOKEN)

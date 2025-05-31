import os
import asyncio
import discord

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
)

def run_discord_bot():            

    @discordClient.event
    async def on_ready():
        global skip_first_loop
        await discordClient.tree.sync()
        await discordClient.send_start_prompt()
        loop = asyncio.get_event_loop()
        loop.create_task(discordClient.process_messages())
        logger.info(f'{discordClient.user} est connecté!')


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

    @discordClient.tree.command(name="help", description="Montre les commandes du bot")
    async def help(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        # Compose persona descriptions from personas.PERSONAS
        persona_lines = []
        for key, value in personas.PERSONAS.items():
            desc = value.get("description", "")[:100]
            persona_lines.append(f"    - `{key}` : {desc}")
        persona_text = "\n".join(persona_lines)
        await interaction.followup.send(f""":crystal_ball: **COMMANDES BASIQUES** :crystal_ball:
- `/chat [message]` Dis moi ce que tu veux savoir.
- `/switchpersona [persona]` Change entre différentes personnalités de Madame Kirma :
{persona_text}
- `/createpersona [name] [description] [prompt]` Ajoute une personnalité custom et l'active immédiatement.
- `/private` Je passe en mode privé (coquinou).
- `/public` Je passe en mode public.
- `/replyall` Bascule entre le mode replyAll et le mode par défaut.
- `/reset` Réinitialise l'historique de la conversation.
- `/lastupdate` Affiche la date et le contenu de la dernière mise à jour du bot.
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

    # Générer dynamiquement les choix pour les personas à partir de personas.PERSONAS
    all_personas = [
        app_commands.Choice(
            name=f"{key.capitalize()} : {value['description'][:50]}...",
            value=key
        )
        for key, value in personas.PERSONAS.items()
    ]

    @discordClient.tree.command(
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

        await interaction.response.defer(thinking=True)
        try:
            # Correction : passe uniquement persona_value
            await discordClient.switch_persona(persona_value)
            personas.current_persona = persona_value
            await interaction.followup.send(
                f"> **INFO : Personnalité changée en `{persona_value}` avec succès.**\nDescription : {personas.PERSONAS[persona_value]['description']}")
        except Exception as e:
            await interaction.followup.send(
                "> **ERREUR : Une erreur est survenue, veuillez réessayer plus tard.**")
            logger.exception(f"Erreur lors du changement de personnalité : {e}")


    @discordClient.tree.command(name="createpersona", description="Ajouter une personnalité custom")
    async def createPersona(interaction: discord.Interaction, name: str, description: str, prompt: str):
        if interaction.user == discordClient.user:
            return

        await interaction.response.defer(thinking=True)
        username = str(interaction.user)
        logger.info(
            f"\x1b[31m{username}\x1b[0m : '/createpersona [{name}] - [{description}]'"
        )

        if name in personas.PERSONAS:
            await interaction.followup.send(
                f"> **ERREUR : Une personnalité avec le nom `{name}` existe déjà.**")
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
                    f"> **INFO : Personnalité `{name}` ajoutée et activée avec succès !**\nDescription : {description}")
                logger.info(f"Custom persona `{name}` added and activated successfully.")
            except Exception as e:
                await interaction.followup.send(
                    "> **ERREUR : Une erreur est survenue lors de l'ajout de la personnalité.**")
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

                    await discordClient.enqueue_message(message, user_message)
            else:
                logger.exception("replying_all_discord_channel_id not found, please use the command `/replyall` again.")

    TOKEN = os.getenv("DISCORD_BOT_TOKEN")

    discordClient.run(TOKEN)

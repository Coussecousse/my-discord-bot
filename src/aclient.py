import os
import discord
import asyncio
import datetime
import json
import random  # Add this import

from src import personas
from src import cultural_theme
from src.log import logger
from utils.message_utils import send_split_message

from dotenv import load_dotenv
from discord import app_commands
from discord.ext import tasks
from asgiref.sync import sync_to_async

import g4f.debug
from g4f.client import Client
from g4f.stubs import ChatCompletion
from g4f.Provider import RetryProvider, OpenaiChat, Aichatos, Liaobots  # gpt-4
from g4f.Provider import Blackbox  # gpt-3.5-turbo

from openai import AsyncOpenAI

g4f.debug.logging = True

load_dotenv()

class discordClient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.chatBot = Client(
            provider=RetryProvider([OpenaiChat, Aichatos, Blackbox, Liaobots], shuffle=False),
        )
        self.chatModel = os.getenv("MODEL")
        self.conversation_history = []
        self.current_channel = None
        self.activity = discord.Activity(type=discord.ActivityType.listening, name="/chat | /help")
        self.isPrivate = False
        self.is_replying_all = os.getenv("REPLYING_ALL")
        self.replying_all_discord_channel_id = os.getenv("REPLYING_ALL_DISCORD_CHANNEL_ID")
        self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_KEY"))
        self.discord_channel_id = os.getenv("DISCORD_CHANNEL_ID")

        config_dir = os.path.abspath(f"{__file__}/../../")
        prompt_name = 'system_prompt.txt'
        prompt_path = os.path.join(config_dir, prompt_name)
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.starting_prompt = f.read()

        self.message_queue = asyncio.Queue()

    async def process_messages(self):
        """Traite les messages en file d'attente."""
        while True:
            try:
                if self.current_channel is not None:
                    while not self.message_queue.empty():
                        async with self.current_channel.typing():
                            message, user_message = await self.message_queue.get()
                            await self.send_message(message, user_message)
                            self.message_queue.task_done()
                await asyncio.sleep(1)
            except Exception as e:
                logger.exception(f"Erreur dans process_messages : {e}")

    async def enqueue_message(self, message, user_message):
        await message.response.defer(ephemeral=self.isPrivate) if self.is_replying_all == "False" else None
        await self.message_queue.put((message, user_message))

    async def send_message(self, message, user_message):
        author = message.user.id if self.is_replying_all == "False" else message.author.id
        user_message_rule = user_message + "Ne fais pas référence à ce message dans ta réponse et suis cette règle : N'oublie pas de répondre avec ta personnalité actuelle pour qu'on puisse la reconnaître dans ta réponse."
        try:
            response = await self.handle_response(user_message_rule)
            response_content = f'> **{user_message}** - <@{str(author)}> \n\n{response}'
            await send_split_message(self, response_content, message)
        except Exception as e:
            logger.exception(f"Error while sending: {e}")

    @tasks.loop(minutes=60)
    async def update_persona_and_daily_message(self):
        """Met à jour la personnalité et envoie un message du jour."""
        try:
            # Met à jour la personnalité uniquement si ce n'est pas une custom
            DAY_PERSONAS = json.loads(os.getenv('DAY_PERSONAS', '{}'))
            today = datetime.datetime.now().weekday()  # 0 = Monday, 6 = Sunday
            new_persona = DAY_PERSONAS.get(str(today), "standard")  # Default: standard

            if personas.current_persona not in personas.PERSONAS or personas.current_persona in DAY_PERSONAS.values():
                if new_persona != personas.current_persona:
                    await self.switch_persona(new_persona)
                    personas.current_persona = new_persona
                    logger.info(f"Personnalité mise à jour : {new_persona}")
                else:
                    logger.info(f"Pas de changement nécessaire. Personnalité actuelle : {personas.current_persona}")
            else:
                logger.info(f"Personnalité custom détectée : {personas.current_persona}. Aucun changement effectué.")

            # Envoie le message du jour si l'heure est correcte
            now = datetime.datetime.now()
            if now.hour == 7:  # Vérifie si l'heure est 7h
                channel = self.get_channel(int(self.discord_channel_id))
                if channel:
                    theme = random.choice(cultural_theme.THEMES)
                    prompt = f"Génère un message du jour sur le thème : {theme}."
                    generated_message = await self.handle_response(prompt)
                    await channel.send(generated_message)
                    logger.info(f"Message du jour envoyé : {generated_message}")
                else:
                    logger.error(f"Canal non trouvé : {self.discord_channel_id}")
            else:
                logger.debug("Pas l'heure d'envoyer le message du jour.")
        except Exception as e:
            logger.exception(f"Erreur dans update_persona_and_daily_message : {e}")

    async def send_start_prompt(self):
        """Envoie le prompt initial et démarre les tâches nécessaires."""
        try:
            if not self.update_persona_and_daily_message.is_running():
                logger.debug("Démarrage de la tâche update_persona_and_daily_message")
                self.update_persona_and_daily_message.start()

            if self.starting_prompt and self.discord_channel_id:
                channel = self.get_channel(int(self.discord_channel_id))
                response = await self.handle_response(self.starting_prompt)
                await channel.send(response)
                logger.info(f"Prompt initial envoyé : {response}")
            else:
                logger.info("Aucun prompt initial ou canal Discord configuré.")
        except Exception as e:
            logger.exception(f"Erreur lors de l'envoi du prompt initial : {e}")

    def reset_conversation_history(self, force_reset=False):
        """Réinitialise l'historique de conversation uniquement si nécessaire."""
        if force_reset or not self.conversation_history:
            self.conversation_history = []
            personas.current_persona = "standard"
            logger.info("Historique de conversation réinitialisé.")
        else:
            logger.debug("Réinitialisation ignorée car l'historique existe déjà.")

    async def switch_persona(self, persona) -> None:
        """Change la personnalité et réinitialise l'historique si nécessaire."""
        self.reset_conversation_history(force_reset=True)
        persona_prompt = personas.PERSONAS.get(persona)
        await self.handle_response(persona_prompt)
        # await self.send_start_prompt()

    async def handle_response(self, user_message) -> str:
        """Gère la réponse en utilisant l'historique de conversation."""
        self.conversation_history.append({'role': 'user', 'content': user_message})

        if os.getenv("OPENAI_ENABLED") == "False":
            async_create = sync_to_async(self.chatBot.chat.completions.create, thread_sensitive=True)
            response: ChatCompletion = await async_create(model=self.chatModel, messages=self.conversation_history)
        else:
            response = await self.openai_client.chat.completions.create(
                model=self.chatModel,
                messages=self.conversation_history
            )

        bot_response = response.choices[0].message.content
        self.conversation_history.append({'role': 'assistant', 'content': bot_response})
        logger.debug(f"Historique mis à jour : {self.conversation_history}")

        return bot_response
discordClient = discordClient()

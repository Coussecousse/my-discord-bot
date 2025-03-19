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
        while True:
            if self.current_channel is not None:
                while not self.message_queue.empty():
                    async with self.current_channel.typing():
                        message, user_message = await self.message_queue.get()
                        try:
                            await self.send_message(message, user_message)
                        except Exception as e:
                            logger.exception(f"Error while processing message: {e}")
                        finally:
                            self.message_queue.task_done()
            await asyncio.sleep(1)

    async def enqueue_message(self, message, user_message):
        await message.response.defer(ephemeral=self.isPrivate) if self.is_replying_all == "False" else None
        await self.message_queue.put((message, user_message))

    async def send_message(self, message, user_message):
        author = message.user.id if self.is_replying_all == "False" else message.author.id
        try:
            response = await self.handle_response(user_message)
            response_content = f'> **{user_message}** - <@{str(author)}> \n\n{response}'
            await send_split_message(self, response_content, message)
        except Exception as e:
            logger.exception(f"Error while sending: {e}")

    @tasks.loop(minutes=60)
    async def update_persona_and_daily_message(self):
        # Met à jour la personnalité
        DAY_PERSONAS = json.loads(os.getenv('DAY_PERSONAS', '{}'))
        today = datetime.datetime.now().weekday()  # 0 = Monday, 6 = Sunday
        new_persona = DAY_PERSONAS.get(str(today), "standard")  # Default: standard

        # Vérifie et met à jour la personnalité
        if new_persona != personas.current_persona:
            try:
                await self.switch_persona(new_persona)
                personas.current_persona = new_persona
                print(f"[INFO] Personnalité mise à jour : {new_persona}")
            except Exception as e:
                print(f"[ERREUR] Impossible de changer de personnalité : {e}")
        else:
            print(f"[INFO] Pas de changement nécessaire. Personnalité actuelle : {personas.current_persona}")

        # Vérifie si l'heure est entre 9h et 10h pour envoyer le message du jour
        now = datetime.datetime.now()
        if now.hour == 8:
            print(f"[DEBUG] Préparation pour envoyer le message du jour à : {now}")
            channel = self.get_channel(int(self.discord_channel_id))
            if channel:
                try:
                    theme = random.choice(cultural_theme.THEMES)  # Use random.choice to select a theme
                    # Prompt pour l'IA
                    prompt = f"Génère un message pour souhaiter une bonne journée et améliorer notre culture générale en nous apprenant quelque chose de nouveau et intéressant sur ce thème : {theme}"

                    generated_message = await self.handle_response(prompt)
                    
                    # Envoie le message généré dans le canal
                    await channel.send(generated_message)
                    print(f"[INFO] Message du jour envoyé : {generated_message}")
                except Exception as e:
                    logger.exception(f"Erreur lors de l'envoi du message du jour : {e}")
            else:
                logger.error(f"Canal non trouvé : {self.discord_channel_id}")
        else:
            print("[DEBUG] Pas l'heure d'envoyer le message du jour.")

    async def send_start_prompt(self):
        try:
            await self.update_persona_and_daily_message()
            if not self.update_persona_and_daily_message.is_running():
                print("DEBUG: Starting update_persona_and_daily_message loop")
                self.update_persona_and_daily_message.start()

            if self.starting_prompt and self.discord_channel_id:
                channel = self.get_channel(int(self.discord_channel_id))
                logger.info(f"Sending system prompt with size {len(self.starting_prompt)}")

                response = await self.handle_response(self.starting_prompt)
                await channel.send(f"{response}")

                logger.info(f"System prompt response: {response}")
            else:
                logger.info("No starting prompt or Discord channel configured. Skipping.")
        except Exception as e:
            logger.exception(f"Error while sending system prompt: {e}")

    def reset_conversation_history(self):
        self.conversation_history = []
        personas.current_persona = "standard"

    async def switch_persona(self, persona) -> None:
        # self.reset_conversation_history()
        persona_prompt = personas.PERSONAS.get(persona)
        await self.handle_response(persona_prompt)
        # await self.send_start_prompt()

    async def handle_response(self, user_message) -> str:
            self.conversation_history.append({'role': 'user', 'content': user_message})
            if len(self.conversation_history) > 26:
                del self.conversation_history[4:6]

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

            return bot_response
discordClient = discordClient()

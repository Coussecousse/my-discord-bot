import os
import discord
import asyncio
import datetime
import json
import random  # Add this import
from datetime import datetime, timedelta

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
import asyncpg  # Add PostgreSQL support

g4f.debug.logging = True

load_dotenv()

class discordClient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # Add this for guild member access
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
        self.web_search_queue = asyncio.Queue()
        self.web_search_mode = os.getenv("WEB_SEARCH_ENABLED")
        self.daily_quiz_state = {}  # {guild_id: {question, answer, deadline, winners}}

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
                
                # Process web search messages
                while not self.web_search_queue.empty():
                    async with self.current_channel.typing():
                        message, user_message = await self.web_search_queue.get()
                        try:
                            await self.send_web_search_message(message, user_message)
                        except Exception as e:
                            logger.exception(f"Error while processing web search message: {e}")
                        finally:
                            self.web_search_queue.task_done()
            await asyncio.sleep(1)

    async def enqueue_message(self, message, user_message):
        await message.response.defer(ephemeral=self.isPrivate) if self.is_replying_all == "False" else None
        await self.message_queue.put((message, user_message))

    async def enqueue_web_search_message(self, message, user_message):
        """Enqueue a message for web search processing"""
        await message.response.defer(ephemeral=self.isPrivate) if self.is_replying_all == "False" else None
        await self.web_search_queue.put((message, user_message))

    async def send_message(self, message, user_message):
        logger.info(f"Starting to process regular message: {user_message}")
        author = message.user.id if self.is_replying_all == "False" else message.author.id
        user_message_rule = user_message + "Ne fais pas référence à ce message dans ta réponse et suis cette règle : N'oublie pas de répondre avec ta personnalité actuelle et exagère là pour qu'on puisse la reconnaître dans ta réponse."
        try:
            response = await self.handle_response(user_message_rule)
            response_content = f'> **{user_message}** - <@{str(author)}> \n\n{response}'
            await send_split_message(self, response_content, message)
        except Exception as e:
            logger.exception(f"Error while sending: {e}")

    async def send_web_search_message(self, message, user_message):
        """Send message with web search capability"""
        author = message.user.id if self.is_replying_all == "False" else message.author.id
        try:
            response = await self.handle_web_search_response(user_message)
            response_content = f'> **{user_message}** - <@{str(author)}> \n\n{response}'
            await send_split_message(self, response_content, message)
        except Exception as e:
            logger.exception(f"Error while sending web search message: {e}")

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
        if now.hour == 7:
            print(f"[DEBUG] Préparation pour envoyer le message du jour à : {now}")
            channel = self.get_channel(int(self.discord_channel_id))
            if channel:
                try:
                    theme = random.choice(cultural_theme.THEMES)  # Use random.choice to select a theme
                    # Prompt pour l'IA
                    prompt = f"Génère un message du jour sans faire référence à ce prompt et améliore notre culture générale en nous apprenant quelque chose de nouveau, de concret, réel et intéressant sur ce thème : {theme}. Rentres dans les détails pour nous en apprendre un maximum comme si nous étions tes élèves mais sans faire référence au fait que nous sommes tes élèves."

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

    async def handle_response(self, user_message, use_web_search=False) -> str:
        if os.getenv("OPENAI_ENABLED") == "False" or self.openai_client is None:
            self.conversation_history.append({'role': 'user', 'content': user_message})
            if len(self.conversation_history) > 26:
                del self.conversation_history[4:6]
            async_create = sync_to_async(self.chatBot.chat.completions.create, thread_sensitive=True)
            response: ChatCompletion = await async_create(model=self.chatModel, messages=self.conversation_history)
            bot_response = response.choices[0].message.content
            self.conversation_history.append({'role': 'assistant', 'content': bot_response})
        else:
            # Try web search if conditions are met, otherwise use regular chat
            if (
                os.getenv("OPENAI_ENABLED") == "True"
                and (use_web_search or self.web_search_mode)
                and self.openai_client is not None
            ):
                try:
                    # Use a web search compatible model
                    web_search_model = os.getenv("WEB_SEARCH_MODEL", "gpt-4.1") 
                    
                    response = await self.openai_client.responses.create(
                        model=web_search_model,
                        tools=[{"type": "web_search_preview", "search_context_size": "low"}],
                        input=user_message
                    )
                    bot_response = response.output_text
                    self.conversation_history.append({'role': 'user', 'content': user_message})
                    self.conversation_history.append({'role': 'assistant', 'content': bot_response})
                    return bot_response
                except Exception as e:
                    logger.warning(f"Web search failed, falling back to regular chat: {e}")
            
            # Regular chat completions (either by choice or fallback from web search)
            bot_response = await self._handle_openai_chat_completion(user_message)

        return bot_response

    async def handle_web_search_response(self, user_message) -> str:
        """Handle responses that require web search capabilities"""
        return await self.handle_response(user_message, use_web_search=True)

    async def _handle_openai_chat_completion(self, user_message) -> str:
        """Handle regular OpenAI chat completions"""
        self.conversation_history.append({'role': 'user', 'content': user_message})
        if len(self.conversation_history) > 26:
            del self.conversation_history[4:6]
        
        response = await self.openai_client.chat.completions.create(
            model=self.chatModel,
            messages=self.conversation_history
        )
        
        bot_response = response.choices[0].message.content
        self.conversation_history.append({'role': 'assistant', 'content': bot_response})
        return bot_response

    def reset_conversation_history(self):
        self.conversation_history = []
        personas.current_persona = "standard"

    async def switch_persona(self, persona) -> None:
        self.reset_conversation_history()
        persona_prompt = personas.PERSONAS.get(persona)
        await self.handle_response(persona_prompt)
        # await self.send_start_prompt()

    async def create_database_for_guild(self, guild: discord.Guild):
        """Crée une base PostgreSQL nommée selon l'id du serveur et une table Users, puis ajoute les membres du serveur."""
        logger.info(f"[DB] Création/connexion à la base pour le serveur {guild.name} ({guild.id})")
        db_user = os.getenv('PGUSER')
        db_password = os.getenv('PGPASSWORD')
        db_host = os.getenv('PGHOST', 'localhost')
        db_port = os.getenv('PGPORT', '5432')
        db_admin = os.getenv('PGADMINDB', 'postgres')
        db_name = f"guild_{guild.id}"
        
        # Connexion à la base d'administration
        conn = await asyncpg.connect(user=db_user, password=db_password, database=db_admin, host=db_host, port=db_port)
        db_exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if not db_exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
        await conn.close()
        
        # Connexion à la base du serveur
        guild_conn = await asyncpg.connect(user=db_user, password=db_password, database=db_name, host=db_host, port=db_port)
        await guild_conn.execute('''
            CREATE TABLE IF NOT EXISTS Users (
                id SERIAL PRIMARY KEY,
                discord_id BIGINT UNIQUE,
                username TEXT,
                score INTEGER DEFAULT 0
            );
        ''')
        logger.info(f"[DB] Table Users créée/vérifiée pour {guild.name} ({guild.id})")
        
        # Ajout des membres du serveur dans la table Users
        await self.insert_guild_members(guild_conn, guild)
        await guild_conn.close()

    async def insert_guild_members(self, conn, guild):
        """Ajoute tous les membres du serveur dans la table Users si non présents."""
        for member in guild.members:
            if not member.bot:
                await conn.execute('''
                    INSERT INTO Users (discord_id, username, score)
                    VALUES ($1, $2, 0)
                    ON CONFLICT (discord_id) DO NOTHING;
                ''', member.id, str(member))
        logger.info(f"[DB] Membres ajoutés/présents dans la table Users pour {guild.name} ({guild.id})")

    def start_daily_quiz_task(self, guild):
        """Démarre la tâche de quiz quotidien pour un serveur."""
        if not hasattr(self, '_quiz_tasks'):
            self._quiz_tasks = {}
        if guild.id not in self._quiz_tasks:
            @tasks.loop(hours=24)
            async def daily_quiz():
                now = datetime.now()
                hour = random.randint(8, 22)
                minute = random.randint(0, 59)
                next_quiz_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                logger.info(f"[QUIZ] Prochain quiz pour {guild.name} ({guild.id}) prévu à {next_quiz_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                if next_quiz_time < now:
                    next_quiz_time += timedelta(days=1)
                
                wait_seconds = (next_quiz_time - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                # Générer une énigme et sa réponse via l'IA
                prompt = "Génère une énigme originale (pas une devinette connue) et donne la réponse. Format : Question: ... Réponse: ..."
                ia_response = await self.handle_response(prompt)
                
                # Extraction question/réponse
                question, answer = None, None
                for line in ia_response.splitlines():
                    if line.lower().startswith("question:"):
                        question = line.split(":", 1)[1].strip()
                    if line.lower().startswith("réponse:") or line.lower().startswith("reponse:"):
                        answer = line.split(":", 1)[1].strip()
                
                if not question or not answer:
                    logger.error(f"[QUIZ] Échec extraction énigme IA : {ia_response}")
                    return  # Ne lance pas le quiz si extraction échouée
                
                deadline = datetime.now() + timedelta(hours=1)
                self.daily_quiz_state[guild.id] = {
                    "question": question,
                    "answer": answer.lower(),
                    "deadline": deadline,
                    "winners": set()
                }
                
                logger.info(f"[QUIZ] Énigme générée pour {guild.name} ({guild.id}) : {question}")
                logger.info(f"[QUIZ] Réponse attendue : {answer}")
                
                channel = self.get_channel(int(self.discord_channel_id))
                if channel:
                    await channel.send(f"🧩 **Énigme du jour !** 🧩\n{question}\nVous avez 1h pour répondre avec /quiz [réponse] !")
                else:
                    logger.error(f"[QUIZ] Canal non trouvé : {self.discord_channel_id}")
            
            self._quiz_tasks[guild.id] = daily_quiz
            daily_quiz.start()

    async def check_quiz_answer(self, guild, user_id, username, answer):
        """Vérifie la réponse à l'énigme du jour."""
        state = self.daily_quiz_state.get(guild.id)
        logger.info(f"[QUIZ] {username} ({user_id}) tente la réponse '{answer}' pour {guild.name} ({guild.id})")
        
        if not state:
            logger.info(f"[QUIZ] Aucune énigme en cours pour {guild.name} ({guild.id})")
            return False, "Aucune énigme en cours."
        
        if datetime.now() > state["deadline"]:
            logger.info(f"[QUIZ] Temps écoulé pour l'énigme du jour ({guild.name} - {guild.id})")
            return False, "Le temps est écoulé pour cette énigme."
        
        if user_id in state["winners"]:
            logger.info(f"[QUIZ] {username} ({user_id}) a déjà répondu correctement aujourd'hui ({guild.name} - {guild.id})")
            return False, "Tu as déjà répondu correctement à l'énigme du jour !"

        # Nettoie la réponse attendue et la réponse donnée pour la comparaison
        expected_answer = state["answer"].strip().lower().rstrip(".")
        user_answer = answer.strip().lower().rstrip(".")
        
        logger.info(f"[QUIZ] Réponse attendue : '{expected_answer}' pour {guild.name} ({guild.id})")
        logger.info(f"[QUIZ] Réponse donnée (nettoyée) : '{user_answer}'")
        
        if user_answer == expected_answer:
            state["winners"].add(user_id)
            # Ajoute 10 points dans la BDD
            db_user = os.getenv('PGUSER')
            db_password = os.getenv('PGPASSWORD')
            db_host = os.getenv('PGHOST', 'localhost')
            db_port = os.getenv('PGPORT', '5432')
            db_name = f"guild_{guild.id}"
            
            try:
                conn = await asyncpg.connect(user=db_user, password=db_password, database=db_name, host=db_host, port=db_port)
                await conn.execute("UPDATE Users SET score = score + 10 WHERE discord_id = $1", user_id)
                await conn.close()
                return True, "Bravo ! Bonne réponse, tu gagnes 10 points !"
            except Exception as e:
                logger.error(f"[QUIZ] Erreur base de données : {e}")
                return True, "Bravo ! Bonne réponse !"
        else:
            return False, "Mauvaise réponse, réessaie !"

discordClient = discordClient()

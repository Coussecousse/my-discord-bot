import os
import discord
import asyncio
import json
import random  # Add this import
import difflib  # Add this import for fuzzy string matching
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo 
from random_word import RandomWords

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
        self.quiz_correct_answers = {}  # Cache des réponses correctes {guild_id: {quiz_id: [user_ids]}}
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

    async def enqueue_web_search_message(self, message, user_message, already_deferred=False):
        """Enqueue a message for web search processing"""
        if not already_deferred and hasattr(message, 'response'):
            try:
                await message.response.defer(ephemeral=self.isPrivate)
            except Exception:
                pass  # Ignore if already deferred or responded
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
        today = datetime.now(ZoneInfo("Europe/Paris")).weekday()  # 0 = Monday, 6 = Sunday
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
        now = datetime.now(ZoneInfo("Europe/Paris"))
        if now.hour == 7:
            print(f"[DEBUG] Préparation pour envoyer le message du jour à : {now}")
            channel = self.get_channel(int(self.discord_channel_id))
            if channel:
                try:
                    theme = random.choice(cultural_theme.THEMES)  # Use random.choice to select a theme
                    # Prompt pour l'IA
                    prompt = (
                        "Génère un message du jour en utilisant ta personnalité actuelle. "
                        "Sélectionne et résume UNIQUEMENT les 5 actualités les plus importantes et pertinentes du JOUR MÊME, "
                        "précises et factuelles. Ne mentionne rien d'avant ou d'après aujourd'hui. "
                        "Le message doit être très condensé, informatif, sans introduction ni conclusion, lisible avec des retours à la ligne. "
                        "AUCUN lien ni URL ne doit apparaître. "
                        "La longueur TOTALE du message doit impérativement rester sous 2000 caractères. "
                        "Si besoin, coupe ou résume davantage. "
                        "Réponds uniquement par le message, sans explication ni ajout."
                    )

                    generated_message = await self.handle_web_search_response(prompt)
                    # Envoie le message généré dans le canal, découpé si trop long
                    max_length = 2000
                    for i in range(0, len(generated_message), max_length):
                        await channel.send(generated_message[i:i+max_length])
                    print(f"[INFO] Message du jour envoyé (découpé si besoin).")
                except Exception as e:
                    logger.exception(f"Erreur lors de l'envoi du message du jour : {e}")
                    print(f"[ERREUR] Erreur lors de l'envoi du message du jour : {e}")
            else:
                logger.error(f"Canal non trouvé : {self.discord_channel_id}")
                print(f"[ERREUR] Canal non trouvé : {self.discord_channel_id}")
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
                print(f"[INFO] Envoi du system prompt (taille : {len(self.starting_prompt)})")
                response = await self.handle_response(self.starting_prompt)
                await channel.send(f"{response}")
                logger.info(f"System prompt response: {response}")
                print(f"[INFO] System prompt envoyé dans le channel {self.discord_channel_id}")
            else:
                logger.info("No starting prompt or Discord channel configured. Skipping.")
                print("[INFO] Aucun system prompt ou channel configuré. Skip.")
        except Exception as e:
            logger.exception(f"Error while sending system prompt: {e}")
            print(f"[ERREUR] Error while sending system prompt: {e}")

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
        persona_data = personas.PERSONAS.get(persona)
        if persona_data and "prompt" in persona_data:
            persona_prompt = persona_data["prompt"]
            await self.handle_response(persona_prompt)
        else:
            logger.warning(f"Persona '{persona}' not found or has no prompt")
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
        
        # Créer aussi la table pour les quiz
        await guild_conn.execute('''
            CREATE TABLE IF NOT EXISTS Quizzes (
                id SERIAL PRIMARY KEY,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                quiz_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                deadline TIMESTAMP NOT NULL,
                is_active BOOLEAN DEFAULT TRUE
            );
        ''')
        
        # Ajouter la table Settings pour stocker les paramètres du serveur
        await guild_conn.execute('''
            CREATE TABLE IF NOT EXISTS Settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        ''')
        
        # Ajout de la table Clues pour suivre les indices demandés
        await guild_conn.execute('''
            CREATE TABLE IF NOT EXISTS Clues (
                id SERIAL PRIMARY KEY,
                quiz_id INTEGER REFERENCES Quizzes(id),
                user_id BIGINT,
                clues_count INTEGER DEFAULT 0,
                UNIQUE (quiz_id, user_id)
            );
        ''')
        
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

    async def get_guild_quiz_channel_id(self, guild_id):
        """Récupère le channel_id du quiz pour un serveur depuis la table Settings."""
        db_user = os.getenv('PGUSER')
        db_password = os.getenv('PGPASSWORD')
        db_host = os.getenv('PGHOST', 'localhost')
        db_port = os.getenv('PGPORT', '5432')
        db_name = f"guild_{guild_id}"
        try:
            conn = await asyncpg.connect(user=db_user, password=db_password, database=db_name, host=db_host, port=db_port)
            await conn.execute('''CREATE TABLE IF NOT EXISTS Settings (key TEXT PRIMARY KEY, value TEXT)''')
            row = await conn.fetchrow("SELECT value FROM Settings WHERE key = 'DISCORD_CHANNEL_ID'")
            await conn.close()
            if row:
                return int(row['value'])
        except Exception as e:
            logger.error(f"[QUIZ] Erreur lors de la récupération du channel_id dans Settings: {e}")
        return int(self.discord_channel_id)  # fallback

    async def set_guild_quiz_channel_id(self, guild_id, channel_id):
        """Met à jour le channel_id du quiz pour un serveur dans la table Settings."""
        db_user = os.getenv('PGUSER')
        db_password = os.getenv('PGPASSWORD')
        db_host = os.getenv('PGHOST', 'localhost')
        db_port = os.getenv('PGPORT', '5432')
        db_name = f"guild_{guild_id}"
        try:
            conn = await asyncpg.connect(user=db_user, password=db_password, database=db_name, host=db_host, port=db_port)
            await conn.execute('''CREATE TABLE IF NOT EXISTS Settings (key TEXT PRIMARY KEY, value TEXT)''')
            await conn.execute('''INSERT INTO Settings (key, value) VALUES ('DISCORD_CHANNEL_ID', $1) ON CONFLICT (key) DO UPDATE SET value = $1''', str(channel_id))
            await conn.close()
            logger.info(f"[QUIZ] Channel quiz mis à jour dans Settings: {channel_id} pour {guild_id}")
        except Exception as e:
            logger.error(f"[QUIZ] Erreur lors de la mise à jour du channel_id dans Settings: {e}")

    @app_commands.command(name="setquizchannel", description="Définit le salon pour les quiz (admin seulement)")
    async def set_quiz_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Slash command pour définir le salon quiz (admin seulement)."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Seuls les administrateurs peuvent utiliser cette commande.", ephemeral=True)
            return
        await self.set_guild_quiz_channel_id(interaction.guild.id, channel.id)
        await interaction.response.send_message(f"✅ Salon quiz mis à jour : {channel.mention}", ephemeral=True)

    async def start_daily_quiz_task(self, guild):
        """Démarre la tâche de quiz quotidien pour un serveur."""
        logger.info(f"[QUIZ] Appel de start_daily_quiz_task pour {guild.name} ({guild.id})")
        if not hasattr(self, '_quiz_tasks'):
            logger.debug("[QUIZ] Création de l'attribut _quiz_tasks")
            self._quiz_tasks = {}
        if guild.id not in self._quiz_tasks:
            logger.info(f"[QUIZ] Initialisation de la loop daily_quiz pour {guild.name} ({guild.id})")
            @tasks.loop(hours=12)  # Toutes les 12h pour avoir 2 quiz par jour
            async def daily_quiz():
                now = datetime.now(ZoneInfo("Europe/Paris"))
                logger.info(f"[QUIZ] daily_quiz déclenché à {now} pour {guild.name} ({guild.id})")
                # Détermine si c'est le quiz du matin (8h-14h) ou de l'après-midi (15h-22h)
                if now.hour < 14:
                    hour = random.randint(8, 14)
                    quiz_type = "matin"
                    logger.info(f"[QUIZ] Sélection du créneau matin pour {guild.name} ({guild.id})")
                else:
                    hour = random.randint(16, 22)
                    quiz_type = "après-midi"
                    logger.info(f"[QUIZ] Sélection du créneau après-midi pour {guild.name} ({guild.id})")
                minute = random.randint(0, 59)
                # next_quiz_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                # TEST
                next_quiz_time = now + timedelta(minutes=1)
                logger.info(f"[QUIZ] Prochain quiz ({quiz_type}) prévu à {next_quiz_time.strftime('%Y-%m-%d %H:%M:%S')} pour {guild.name} ({guild.id})")
                if next_quiz_time < now:
                    logger.debug(f"[QUIZ] next_quiz_time < now, ajout de 12h")
                    next_quiz_time += timedelta(hours=12)
                wait_seconds = (next_quiz_time - now).total_seconds()
                logger.info(f"[QUIZ] Attente de {wait_seconds:.0f} secondes avant le prochain quiz pour {guild.name} ({guild.id})")
                await asyncio.sleep(wait_seconds)
                logger.info(f"[QUIZ] Génération de l'énigme IA pour {guild.name} ({guild.id})")
                
                # Generate a random word
                r = RandomWords()
                random_word_en = r.get_random_word()
                prompt = f"""Le mot anglais choisi est : "{random_word_en}".
Traduis ce mot en français, puis génère une énigme originale ou une charade sur ce mot français.

RÈGLES IMPORTANTES :
- La réponse doit être UN SEUL MOT ou UNE EXPRESSION COURTE (maximum 3 mots)
- Pas de phrase complète comme réponse
- Pas d'explication ou d'artifice dans la réponse
- Seulement le mot/expression exact
- La réponse doit IMPÉRATIVEMENT être le mot français traduit depuis : "{random_word_en}"

Format obligatoire :
Question: [énigme ici]
Réponse: [mot ou expression courte seulement]

Exemples :
Question: Je suis rond, je roule, mais je ne suis pas une roue. On me mange et je peux être sucré ou salé.
Réponse: biscuit

Question: Plus je suis percé, plus je tiens fermement.
Réponse: ceinture
"""
                ia_response = await self.handle_response(prompt)
                logger.info(f"[QUIZ] Réponse IA brute : {ia_response}")
                # Extraction question/réponse
                question, answer = None, None
                for line in ia_response.splitlines():
                    if line.lower().startswith("question:"):
                        question = line.split(":", 1)[1].strip()
                    if line.lower().startswith("réponse:") or line.lower().startswith("reponse:"):
                        answer = line.split(":", 1)[1].strip()
                logger.info(f"[QUIZ] Extraction : question='{question}', answer='{answer}' pour {guild.name} ({guild.id})")
                if not question or not answer:
                    logger.error(f"[QUIZ] Échec extraction énigme IA : {ia_response}")
                    return  # Ne lance pas le quiz si extraction échouée
                deadline = datetime.now(ZoneInfo("Europe/Paris")) + timedelta(hours=1)
                deadline = deadline.replace(tzinfo=None)
                # TEST
                # deadline = next_quiz_time + timedelta(minutes=1)
                logger.info(f"[QUIZ] Deadline du quiz : {deadline} pour {guild.name} ({guild.id})")
                # Insérer le quiz dans la base de données du serveur
                db_user = os.getenv('PGUSER')
                db_password = os.getenv('PGPASSWORD')
                db_host = os.getenv('PGHOST', 'localhost')
                db_port = os.getenv('PGPORT', '5432')
                db_name = f"guild_{guild.id}"
                try:
                    logger.info(f"[QUIZ] Connexion à la base {db_name} pour {guild.name} ({guild.id})")
                    conn = await asyncpg.connect(user=db_user, password=db_password, database=db_name, host=db_host, port=db_port)
                    await conn.execute("UPDATE Quizzes SET is_active = FALSE WHERE is_active = TRUE")
                    logger.info(f"[QUIZ] Anciens quiz désactivés pour {guild.name} ({guild.id})")
                    if guild.id in self.quiz_correct_answers:
                        self.quiz_correct_answers[guild.id].clear()
                        logger.info(f"[QUIZ] Cache des bonnes réponses vidé pour {guild.name} ({guild.id})")
                    quiz_id = await conn.fetchval('''
                        INSERT INTO Quizzes (question, answer, quiz_type, deadline)
                        VALUES ($1, $2, $3, $4)
                        RETURNING id
                    ''', question, answer.lower(), quiz_type, deadline)
                    await conn.close()
                    logger.info(f"[QUIZ] Énigme ({quiz_type}) générée et enregistrée (ID: {quiz_id}) pour {guild.name} ({guild.id}) : {question}")
                    logger.info(f"[QUIZ] Réponse attendue : {answer}")
                    # Récupérer le salon de quiz depuis la base
                    quiz_channel_id = await self.get_guild_quiz_channel_id(guild.id)
                    if quiz_channel_id:
                        channel = self.get_channel(quiz_channel_id)
                    else:
                        channel = self.get_channel(int(self.discord_channel_id)) if self.discord_channel_id else None

                    if channel and getattr(channel, 'guild', None) and channel.guild.id == guild.id:
                        print(f"[QUIZ] Envoi de l'énigme dans le channel {channel.id} pour {guild.name} ({guild.id})")
                        # DEBUG
                        emoji = "🌅" if quiz_type == "matin" else "🌆"
                        await channel.send(f"{emoji} **Énigme !** {emoji}\n{question}\nVous avez 1h pour répondre avec /quiz [réponse] !")
                        logger.info(f"[QUIZ] Énigme envoyée dans le channel {channel.id} pour {guild.name} ({guild.id})")
                        asyncio.create_task(self._announce_quiz_answer_after_delay(guild.id, quiz_id, question, answer, quiz_type, channel, 3600))
                        # TEST
                        # asyncio.create_task(self._announce_quiz_answer_after_delay(guild.id, quiz_id, question, answer, quiz_type, channel, 60))
                        logger.info(f"[QUIZ] Tâche d'annonce de la réponse programmée pour {guild.name} ({guild.id})")
                    else:
                        logger.error(f"[QUIZ] Canal non trouvé ou n'appartient pas au serveur : {getattr(channel, 'id', None)} pour {guild.name} ({guild.id})")
                except Exception as e:
                    logger.error(f"[QUIZ] Erreur base de données lors de la création du quiz : {e}")
            self._quiz_tasks[guild.id] = daily_quiz
            logger.info(f"[QUIZ] Lancement de la loop daily_quiz pour {guild.name} ({guild.id})")
            daily_quiz.start()

    async def _announce_quiz_answer_after_delay(self, guild_id, quiz_id, question, answer, quiz_type, channel, delay_seconds):
        """
        Annonce la réponse du quiz après un délai spécifié (par défaut 1h).
        """
        try:
            # Attendre le délai spécifié
            await asyncio.sleep(delay_seconds)
            
            logger.info(f"[QUIZ] Délai écoulé pour le quiz {quiz_id} ({quiz_type}) du serveur {guild_id}")
            
            # Marquer le quiz comme inactif dans la base de données
            db_user = os.getenv('PGUSER')
            db_password = os.getenv('PGPASSWORD')
            db_host = os.getenv('PGHOST', 'localhost')
            db_port = os.getenv('PGPORT', '5432')
            db_name = f"guild_{guild_id}"
            
            conn = await asyncpg.connect(user=db_user, password=db_password, database=db_name, host=db_host, port=db_port)
            
            # Marquer le quiz comme inactif
            await conn.execute("UPDATE Quizzes SET is_active = FALSE WHERE id = $1", quiz_id)
            
            await conn.close()
            
            # Annoncer la fin du quiz et la réponse
            emoji = "🌅" if quiz_type == "matin" else "🌆"
            end_message = f"{emoji} **Fin du quiz** {emoji}\n\n"
            end_message += f"**Question :** {question}\n"
            end_message += f"**Réponse :** {answer}\n\n"
            
            await channel.send(end_message)
            logger.info(f"[QUIZ] Annonce de fin diffusée pour le quiz {quiz_id} ({quiz_type}) du serveur {guild_id}")
            
        except Exception as e:
            logger.error(f"[QUIZ] Erreur lors de l'annonce de fin du quiz {quiz_id} : {e}")

    async def check_quiz_answer(self, guild, user_id, username, answer):
        """Vérifie la réponse à l'énigme du jour."""
        logger.info(f"[QUIZ] {username} ({user_id}) tente la réponse '{answer}' pour {guild.name} ({guild.id})")
        
        # Connexion à la base de données du serveur
        db_user = os.getenv('PGUSER')
        db_password = os.getenv('PGPASSWORD')
        db_host = os.getenv('PGHOST', 'localhost')
        db_port = os.getenv('PGPORT', '5432')
        db_name = f"guild_{guild.id}"
        
        try:
            conn = await asyncpg.connect(user=db_user, password=db_password, database=db_name, host=db_host, port=db_port)
            
            # Chercher le quiz actif pour ce serveur
            active_quiz = await conn.fetchrow('''
                SELECT id, question, answer, quiz_type, deadline 
                FROM Quizzes 
                WHERE is_active = TRUE AND deadline > NOW()
                ORDER BY created_at DESC 
                LIMIT 1
            ''')
            
            if not active_quiz:
                await conn.close()
                logger.info(f"[QUIZ] Aucune énigme en cours pour {guild.name} ({guild.id})")
                return False, "Aucune énigme en cours."
            
            quiz_id = active_quiz['id']
            
            # Vérifier si l'utilisateur a déjà répondu correctement à ce quiz (cache en mémoire)
            if guild.id in self.quiz_correct_answers and quiz_id in self.quiz_correct_answers[guild.id]:
                if user_id in self.quiz_correct_answers[guild.id][quiz_id]:
                    await conn.close()
                    quiz_type = active_quiz['quiz_type']
                    logger.info(f"[QUIZ] {username} ({user_id}) a déjà répondu correctement à l'énigme du {quiz_type} ({guild.name} - {guild.id})")
                    return False, f"Tu as déjà répondu correctement à l'énigme du {quiz_type} !"

            # Nettoie et normalise la réponse attendue et la réponse donnée
            expected_answer = self._normalize_answer(active_quiz['answer'])
            user_answer = self._normalize_answer(answer)
            
            logger.info(f"[QUIZ] Réponse attendue (normalisée) : '{expected_answer}' pour {guild.name} ({guild.id})")
            logger.info(f"[QUIZ] Réponse donnée (normalisée) : '{user_answer}'")
            
            # Calcul de la similarité avec difflib
            similarity = difflib.SequenceMatcher(None, expected_answer, user_answer).ratio()
            similarity_threshold = 0.80  # Seuil de similarité (80%)
            
            logger.info(f"[QUIZ] Similarité calculée : {similarity:.2f} (seuil: {similarity_threshold})")
            
            # Accepter la réponse si elle est identique ou suffisamment similaire
            # Calcul du score en fonction des indices demandés
            clues_row = await conn.fetchrow('SELECT clues_count FROM Clues WHERE quiz_id = $1 AND user_id = $2', quiz_id, user_id)
            clues_count = clues_row['clues_count'] if clues_row else 0
            score = max(10 - 2 * clues_count, 4)

            # Accepter la réponse si elle est identique ou suffisamment similaire
            if user_answer == expected_answer or similarity >= similarity_threshold:
                # Ajouter le score à l'utilisateur
                await conn.execute("UPDATE Users SET score = score + $1 WHERE discord_id = $2", score, user_id)
                
                # Marquer la réponse comme correcte dans le cache
                if guild.id not in self.quiz_correct_answers:
                    self.quiz_correct_answers[guild.id] = {}
                if quiz_id not in self.quiz_correct_answers[guild.id]:
                    self.quiz_correct_answers[guild.id][quiz_id] = []
                self.quiz_correct_answers[guild.id][quiz_id].append(user_id)
                
                await conn.close()
                quiz_type = active_quiz['quiz_type']
                
                # Message différent selon si c'est une correspondance exacte ou similaire
                if user_answer == expected_answer:
                    return True, f"Bravo ! Bonne réponse, tu gagnes {score} points !"
                else:
                    return True, f"Bravo ! Ta réponse est suffisamment proche de la réponse attendue. Tu gagnes {score} points !"
            else:
                await conn.close()
                return False, "Mauvaise réponse, réessaie !"
                
        except Exception as e:
            logger.error(f"[QUIZ] Erreur base de données : {e}")
            return False, "Erreur technique, veuillez réessayer plus tard."

    def _normalize_answer(self, answer):
        """
        Normalise une réponse en enlevant les articles et mots courants
        pour améliorer la correspondance floue.
        """
        # Convertir en minuscules et enlever la ponctuation
        normalized = answer.strip().lower().rstrip(".,!?;:")
        
        # Articles et mots courants à enlever du début
        common_words = ['le ', 'la ', 'les ', 'un ', 'une ', 'des ', 'du ', 'de la ', 'de l\'', 'de ', 'd\'', 'l\'']
        
        for word in common_words:
            if normalized.startswith(word):
                normalized = normalized[len(word):].strip()
                break  # Ne supprimer qu'un seul article au début
        
        return normalized

    async def request_quiz_clue(self, guild, user_id):
        """Permet à un utilisateur de demander un indice pour le quiz actif."""
        db_user = os.getenv('PGUSER')
        db_password = os.getenv('PGPASSWORD')
        db_host = os.getenv('PGHOST', 'localhost')
        db_port = os.getenv('PGPORT', '5432')
        db_name = f"guild_{guild.id}"

        try:
            conn = await asyncpg.connect(user=db_user, password=db_password, database=db_name, host=db_host, port=db_port)
            active_quiz = await conn.fetchrow('''
                SELECT id, question, answer FROM Quizzes WHERE is_active = TRUE AND deadline > NOW() ORDER BY created_at DESC LIMIT 1
            ''')
            if not active_quiz:
                await conn.close()
                return False, "Aucune énigme en cours."

            quiz_id = active_quiz['id']
            clue_row = await conn.fetchrow('SELECT clues_count FROM Clues WHERE quiz_id = $1 AND user_id = $2', quiz_id, user_id)
            clues_count = clue_row['clues_count'] if clue_row else 0

            if clues_count >= 3:
                await conn.close()
                return False, "Tu as déjà demandé le maximum d'indices (3) pour cette énigme."

            # Générer un indice via l'IA (exemple simple : demander une explication du mot)
            prompt = f"Donne un indice pour deviner le mot suivant (sans donner la réponse) : {active_quiz['question']}"
            clue = await self.handle_response(prompt)

            # Mettre à jour le nombre d'indices demandés
            if clue_row:
                await conn.execute('UPDATE Clues SET clues_count = clues_count + 1 WHERE quiz_id = $1 AND user_id = $2', quiz_id, user_id)
            else:
                await conn.execute('INSERT INTO Clues (quiz_id, user_id, clues_count) VALUES ($1, $2, 1)', quiz_id, user_id)

            await conn.close()
            return True, clue
        except Exception as e:
            logger.error(f"[QUIZ] Erreur lors de la demande d'indice : {e}")
            return False, "Erreur technique, veuillez réessayer plus tard."

discordClient = discordClient()

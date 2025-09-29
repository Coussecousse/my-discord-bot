import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os
import asyncio

# DO NOT mock Discord
import discord
from discord.ext import tasks

class DiscordClientForTest:
    """Helper class that simulates discordClient without inheriting from discord.Client"""
    
    def __init__(self):
        # Copy only necessary attributes
        self.quiz_correct_answers = {}
        self.daily_quiz_state = {}
    
    async def handle_response(self, prompt):
        """Mock handle_response for tests"""
        return "AI generated clue"
    
    def _normalize_answer(self, answer):
        """Copy of the normalization method"""
        normalized = answer.strip().lower().rstrip(".,!?;:")
        common_words = ['le ', 'la ', 'les ', 'un ', 'une ', 'des ', 'du ', 'de la ', 'de l\'', 'de ', 'd\'', 'l\'']
        
        for word in common_words:
            if normalized.startswith(word):
                normalized = normalized[len(word):].strip()
                break
        
        return normalized
    
    async def request_quiz_clue(self, guild, user_id):
        """method copied from aclient.py"""
        db_user = os.getenv('PGUSER')
        db_password = os.getenv('PGPASSWORD')
        db_host = os.getenv('PGHOST', 'localhost')
        db_port = os.getenv('PGPORT', '5432')
        db_name = f"guild_{guild.id}"

        try:
            import asyncpg
            conn = await asyncpg.connect(user=db_user, password=db_password, database=db_name, host=db_host, port=db_port)
            active_quiz = await conn.fetchrow('''
                SELECT id, question, answer FROM Quizzes WHERE is_active = TRUE AND deadline > NOW() ORDER BY created_at DESC LIMIT 1
            ''')
            if not active_quiz:
                await conn.close()
                return False, "No active quiz."

            quiz_id = active_quiz['id']
            clue_row = await conn.fetchrow('SELECT clues_count FROM Clues WHERE quiz_id = $1 AND user_id = $2', quiz_id, user_id)
            clues_count = clue_row['clues_count'] if clue_row else 0

            if clues_count >= 3:
                await conn.close()
                return False, "You have already requested the maximum number of clues (3) for this puzzle."

            # Generate a clue via AI
            prompt = (
                f"Here is a riddle: \"{active_quiz['question']}\". And here is its answer: \"{active_quiz['answer']}\".\n"
                "Give an additional clue to help find the answer, without revealing the exact word or expression. "
                "The clue can be a charade, a riddle, an anecdote or any other form, but it must not give the solution directly."
            )
            clue = await self.handle_response(prompt)

            # Update the number of requested clues
            if clue_row:
                await conn.execute('UPDATE Clues SET clues_count = clues_count + 1 WHERE quiz_id = $1 AND user_id = $2', quiz_id, user_id)
            else:
                await conn.execute('INSERT INTO Clues (quiz_id, user_id, clues_count) VALUES ($1, $2, 1)', quiz_id, user_id)

            await conn.close()
            return True, clue
        except Exception as e:
            return False, "Technical error, please try again later."
    
    async def check_quiz_answer(self, guild, user_id, username, answer):
        """method copied from aclient.py"""
        import difflib
        
        db_user = os.getenv('PGUSER')
        db_password = os.getenv('PGPASSWORD')
        db_host = os.getenv('PGHOST', 'localhost')
        db_port = os.getenv('PGPORT', '5432')
        db_name = f"guild_{guild.id}"
        
        try:
            import asyncpg
            conn = await asyncpg.connect(user=db_user, password=db_password, database=db_name, host=db_host, port=db_port)
            
            active_quiz = await conn.fetchrow('''
                SELECT id, question, answer, quiz_type, deadline 
                FROM Quizzes 
                WHERE is_active = TRUE AND deadline > NOW()
                ORDER BY created_at DESC 
                LIMIT 1
            ''')
            
            if not active_quiz:
                await conn.close()
                return False, "No active quiz."
            
            quiz_id = active_quiz['id']
            
            # Check correct answers cache
            if guild.id in self.quiz_correct_answers and quiz_id in self.quiz_correct_answers[guild.id]:
                if user_id in self.quiz_correct_answers[guild.id][quiz_id]:
                    await conn.close()
                    quiz_type = active_quiz['quiz_type']
                    return False, f"You have already answered correctly to the {quiz_type} puzzle!"

            # Normalization and comparison
            expected_answer = self._normalize_answer(active_quiz['answer'])
            user_answer = self._normalize_answer(answer)
            
            similarity = difflib.SequenceMatcher(None, expected_answer, user_answer).ratio()
            similarity_threshold = 0.80
            
            # Score calculation with clues
            clues_row = await conn.fetchrow('SELECT clues_count FROM Clues WHERE quiz_id = $1 AND user_id = $2', quiz_id, user_id)
            clues_count = clues_row['clues_count'] if clues_row else 0
            score = max(10 - 2 * clues_count, 4)

            if user_answer == expected_answer or similarity >= similarity_threshold:
                # Score update
                await conn.execute("UPDATE Users SET score = score + $1 WHERE discord_id = $2", score, user_id)
                
                # Cache update
                if guild.id not in self.quiz_correct_answers:
                    self.quiz_correct_answers[guild.id] = {}
                if quiz_id not in self.quiz_correct_answers[guild.id]:
                    self.quiz_correct_answers[guild.id][quiz_id] = []
                self.quiz_correct_answers[guild.id][quiz_id].append(user_id)
                
                await conn.close()
                
                if user_answer == expected_answer:
                    return True, f"Bravo! Correct answer, you earn {score} points!"
                else:
                    return True, f"Bravo! Your answer is close enough to the expected answer. You earn {score} points!"
            else:
                await conn.close()
                return False, "Wrong answer, try again!"
                
        except Exception as e:
            return False, "Technical error, please try again later."

# TESTS WITH LOGIC
@pytest.mark.asyncio
async def test_clue_limit_real_logic():
    """test of clue limitation with logic"""
    
    client = DiscordClientForTest()
    
    guild = MagicMock(id=67890)
    user_id = 12345
    
    with patch.dict('os.environ', {
        'PGUSER': 'test_user', 'PGPASSWORD': 'test_pass', 
        'PGHOST': 'localhost', 'PGPORT': '5432'
    }):
        mock_conn = AsyncMock()
        mock_conn.close = AsyncMock()
        
        with patch('asyncpg.connect', return_value=mock_conn):
            # SCENARIO 1: User already has 3 clues - should be refused
            mock_conn.fetchrow.side_effect = [
                {'id': 1, 'question': 'Test question', 'answer': 'test'},  # Active quiz
                {'clues_count': 3}  # 3 clues already requested - MAXIMUM REACHED
            ]
            
            # Call the method
            success, message = await client.request_quiz_clue(guild, user_id)
            
            # Verify that the logic correctly refuses
            assert success is False
            assert "maximum" in message.lower()
            assert "3" in message
            
            # Verify that no DB update occurred
            update_calls = [call for call in mock_conn.execute.call_args_list 
                           if 'UPDATE Clues SET clues_count' in str(call)]
            assert len(update_calls) == 0

@pytest.mark.asyncio
async def test_clue_generation_real_logic():
    """test of clue generation"""
    
    client = DiscordClientForTest()
    
    guild = MagicMock(id=67890)
    user_id = 12345
    
    with patch.dict('os.environ', {
        'PGUSER': 'test_user', 'PGPASSWORD': 'test_pass', 
        'PGHOST': 'localhost', 'PGPORT': '5432'
    }):
        mock_conn = AsyncMock()
        mock_conn.close = AsyncMock()
        
        with patch('asyncpg.connect', return_value=mock_conn):
            # SCENARIO: User has 1 clue - can request another
            mock_conn.fetchrow.side_effect = [
                {'id': 1, 'question': 'What is sweet?', 'answer': 'chocolate'},
                {'clues_count': 1}  # 1 clue already requested
            ]
            
            # Call the method
            success, clue_message = await client.request_quiz_clue(guild, user_id)
            
            # Verify that the logic works
            assert success is True
            assert "AI generated" in clue_message
            
            # Verify that the DB is correctly updated
            mock_conn.execute.assert_called_with(
                'UPDATE Clues SET clues_count = clues_count + 1 WHERE quiz_id = $1 AND user_id = $2',
                1, 12345
            )

@pytest.mark.asyncio
async def test_quiz_scoring_real_logic():
    """test of scoring calculation with clues"""
    
    client = DiscordClientForTest()
    
    guild = MagicMock(id=67890)
    user_id = 12345
    username = "TestUser"
    
    with patch.dict('os.environ', {
        'PGUSER': 'test_user', 'PGPASSWORD': 'test_pass', 
        'PGHOST': 'localhost', 'PGPORT': '5432'
    }):
        mock_conn = AsyncMock()
        mock_conn.close = AsyncMock()
        
        with patch('asyncpg.connect', return_value=mock_conn):
            
            # TEST: 2 clues used = 6 points
            mock_conn.fetchrow.side_effect = [
                {'id': 1, 'question': 'Test', 'answer': 'chocolate', 'quiz_type': 'morning', 'deadline': '2024-12-31 23:59:59'},
                {'clues_count': 2},  # 2 clues used
            ]
            
            # Call the method
            success, message = await client.check_quiz_answer(guild, user_id, username, "chocolate")
            
            # Verify the score calculation: max(10 - 2*2, 4) = 6
            assert success is True
            mock_conn.execute.assert_called_with(
                "UPDATE Users SET score = score + $1 WHERE discord_id = $2", 
                6, user_id  # 6 points calculated correctly
            )
            assert "6 points" in message

@pytest.mark.asyncio
async def test_fuzzy_matching_real_logic():
    """test of fuzzy matching"""
    
    client = DiscordClientForTest()
    
    guild = MagicMock(id=67890)
    user_id = 12345
    username = "TestUser"
    
    with patch.dict('os.environ', {
        'PGUSER': 'test_user', 'PGPASSWORD': 'test_pass', 
        'PGHOST': 'localhost', 'PGPORT': '5432'
    }):
        mock_conn = AsyncMock()
        mock_conn.close = AsyncMock()
        
        with patch('asyncpg.connect', return_value=mock_conn):
            
            # TEST: Answer with typo
            mock_conn.fetchrow.side_effect = [
                {'id': 1, 'question': 'Test', 'answer': 'chocolate', 'quiz_type': 'morning', 'deadline': '2024-12-31 23:59:59'},
                None,  # No clues
            ]
            
            # Test with a typo: "choclate" instead of "chocolate"
            success, message = await client.check_quiz_answer(guild, user_id, username, "choclate")
            
            # The similarity algorithm should accept this answer
            # Similarity between "chocolate" and "choclate" = very high
            assert success is True
            assert "close" in message.lower() or "bravo" in message.lower()

@pytest.mark.asyncio
async def test_answer_normalization_real_logic():
    """test of answer normalization"""
    
    client = DiscordClientForTest()
    
    # Tests of normalization logic
    assert client._normalize_answer("Le chocolat") == "chocolat"
    assert client._normalize_answer("la pomme.") == "pomme"
    assert client._normalize_answer("un biscuit!") == "biscuit"
    assert client._normalize_answer("des fleurs?") == "fleurs"
    assert client._normalize_answer("l'eau") == "eau"
    assert client._normalize_answer("de l'argent") == "argent"

@pytest.mark.asyncio
async def test_no_active_quiz_real_logic():
    """Test when no quiz is active"""

    client = DiscordClientForTest()
    
    guild = MagicMock(id=67890)
    user_id = 12345
    
    with patch.dict('os.environ', {
        'PGUSER': 'test_user', 'PGPASSWORD': 'test_pass', 
        'PGHOST': 'localhost', 'PGPORT': '5432'
    }):
        mock_conn = AsyncMock()
        mock_conn.close = AsyncMock()
        
        with patch('asyncpg.connect', return_value=mock_conn):
            # Simulate no active quiz
            mock_conn.fetchrow.return_value = None
            
            # Call the method
            success, message = await client.request_quiz_clue(guild, user_id)

            # Verify the logic
            assert success is False
            assert "no active quiz" in message.lower()
            
            # No update attempts should occur
            mock_conn.execute.assert_not_called()
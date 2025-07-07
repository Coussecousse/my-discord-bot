#!/usr/bin/env python3
"""
Test de la logique simplifiée des quiz sans table quiz_winners.
"""

class MockQuizClient:
    def __init__(self):
        self.quiz_correct_answers = {}  # Cache des réponses correctes {guild_id: {quiz_id: [user_ids]}}
    
    def simulate_correct_answer(self, guild_id, quiz_id, user_id, username):
        """Simule une réponse correcte."""
        # Marquer la réponse comme correcte dans le cache
        if guild_id not in self.quiz_correct_answers:
            self.quiz_correct_answers[guild_id] = {}
        if quiz_id not in self.quiz_correct_answers[guild_id]:
            self.quiz_correct_answers[guild_id][quiz_id] = []
        
        if user_id in self.quiz_correct_answers[guild_id][quiz_id]:
            return False, f"Tu as déjà répondu correctement à ce quiz !"
        
        self.quiz_correct_answers[guild_id][quiz_id].append(user_id)
        return True, f"Bravo {username} ! Bonne réponse, tu gagnes 10 points !"
    
    def start_new_quiz(self, guild_id, quiz_id):
        """Simule le démarrage d'un nouveau quiz."""
        # Nettoyer le cache des réponses correctes pour ce serveur
        if guild_id in self.quiz_correct_answers:
            self.quiz_correct_answers[guild_id].clear()
        print(f"🆕 Nouveau quiz {quiz_id} pour le serveur {guild_id} - cache nettoyé")

def test_simplified_quiz_logic():
    """Test de la logique simplifiée des quiz."""
    print("🧪 Test de la logique simplifiée des quiz")
    print("-" * 50)
    
    client = MockQuizClient()
    
    guild_id = 123456
    quiz_id_1 = 1
    quiz_id_2 = 2
    
    # Test 1: Première réponse correcte
    print("Test 1: Première réponse correcte")
    success, message = client.simulate_correct_answer(guild_id, quiz_id_1, 1001, "Alice")
    print(f"Résultat: {success} - {message}")
    
    # Test 2: Deuxième utilisateur répond correctement
    print("\nTest 2: Deuxième utilisateur répond correctement")
    success, message = client.simulate_correct_answer(guild_id, quiz_id_1, 1002, "Bob")
    print(f"Résultat: {success} - {message}")
    
    # Test 3: Alice essaie de répondre à nouveau
    print("\nTest 3: Alice essaie de répondre à nouveau")
    success, message = client.simulate_correct_answer(guild_id, quiz_id_1, 1001, "Alice")
    print(f"Résultat: {success} - {message}")
    
    # Test 4: Nouveau quiz démarre
    print("\nTest 4: Nouveau quiz démarre")
    client.start_new_quiz(guild_id, quiz_id_2)
    
    # Test 5: Alice peut maintenant répondre au nouveau quiz
    print("\nTest 5: Alice répond au nouveau quiz")
    success, message = client.simulate_correct_answer(guild_id, quiz_id_2, 1001, "Alice")
    print(f"Résultat: {success} - {message}")
    
    # État final du cache
    print(f"\n📊 État final du cache: {client.quiz_correct_answers}")
    
    print("\n✅ Test terminé avec succès !")

if __name__ == "__main__":
    test_simplified_quiz_logic()

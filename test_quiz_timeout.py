#!/usr/bin/env python3
"""
Script de test pour valider la logique d'annonce automatique des réponses de quiz.
"""

import asyncio
from datetime import datetime, timedelta

async def test_quiz_timeout_logic():
    """Simule le délai et l'annonce de fin de quiz."""
    print("🧪 Test de la logique d'annonce automatique de quiz")
    print("-" * 50)
    
    # Simule les données d'un quiz
    quiz_data = {
        "quiz_id": 123,
        "guild_id": 456789,
        "question": "Je suis rond, je roule, mais je ne suis pas une roue. On me mange et je peux être sucré ou salé.",
        "answer": "biscuit",
        "quiz_type": "matin",
        "delay_seconds": 5  # 5 secondes pour le test au lieu de 3600
    }
    
    print(f"📋 Quiz ID: {quiz_data['quiz_id']}")
    print(f"🏰 Serveur ID: {quiz_data['guild_id']}")
    print(f"❓ Question: {quiz_data['question']}")
    print(f"✅ Réponse: {quiz_data['answer']}")
    print(f"🌅 Type: {quiz_data['quiz_type']}")
    print(f"⏰ Délai: {quiz_data['delay_seconds']} secondes")
    print()
    
    # Simule le démarrage du quiz
    print("🚀 Démarrage du quiz...")
    start_time = datetime.now()
    
    # Simule l'attente du délai
    print(f"⏳ Attente de {quiz_data['delay_seconds']} secondes...")
    await asyncio.sleep(quiz_data['delay_seconds'])
    
    # Simule l'annonce de fin
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    
    print(f"⏰ Délai écoulé ! ({elapsed:.1f}s)")
    print()
    
    # Simule l'annonce de fin
    emoji = "🌅" if quiz_data['quiz_type'] == "matin" else "🌆"
    
    # Cas 1: Aucun gagnant
    print(f"{emoji} **Fin du quiz du {quiz_data['quiz_type']}** {emoji}")
    print(f"**Question :** {quiz_data['question']}")
    print(f"**Réponse :** {quiz_data['answer']}")
    print("😔 Personne n'a trouvé la bonne réponse cette fois-ci. Bonne chance pour le prochain quiz !")
    print()
    
    # Cas 2: Un gagnant
    print("--- Simulation avec 1 gagnant ---")
    print(f"{emoji} **Fin du quiz du {quiz_data['quiz_type']}** {emoji}")
    print(f"**Question :** {quiz_data['question']}")
    print(f"**Réponse :** {quiz_data['answer']}")
    print("🎉 Félicitations à **Alice** qui a trouvé la bonne réponse !")
    print()
    
    # Cas 3: Plusieurs gagnants
    print("--- Simulation avec 3 gagnants ---")
    print(f"{emoji} **Fin du quiz du {quiz_data['quiz_type']}** {emoji}")
    print(f"**Question :** {quiz_data['question']}")
    print(f"**Réponse :** {quiz_data['answer']}")
    print("🎉 Félicitations à **Alice, Bob et **Charlie** qui ont trouvé la bonne réponse !")
    print()
    
    print("✅ Test terminé avec succès !")

if __name__ == "__main__":
    asyncio.run(test_quiz_timeout_logic())

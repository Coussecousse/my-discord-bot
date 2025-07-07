#!/usr/bin/env python3
"""
Script de test pour vérifier la logique de correspondance floue
des réponses de quiz du bot Discord.
"""

import difflib

def normalize_answer(answer):
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

def test_similarity(expected, given, threshold=0.80):
    """Teste la similarité entre deux réponses."""
    expected_norm = normalize_answer(expected)
    given_norm = normalize_answer(given)
    
    similarity = difflib.SequenceMatcher(None, expected_norm, given_norm).ratio()
    
    print(f"Expected: '{expected}' -> '{expected_norm}'")
    print(f"Given: '{given}' -> '{given_norm}'")
    print(f"Similarity: {similarity:.2f} (threshold: {threshold})")
    print(f"Result: {'✅ ACCEPTÉ' if similarity >= threshold else '❌ REFUSÉ'}")
    print("-" * 50)
    
    return similarity >= threshold

if __name__ == "__main__":
    print("Test de la logique de correspondance floue pour les quiz\n")
    
    # Tests avec des exemples réalistes
    test_cases = [
        ("biscuit", "biscuit"),           # Exact match
        ("biscuit", "un biscuit"),        # Avec article
        ("biscuit", "le biscuit"),        # Avec article différent
        ("pain", "du pain"),              # Avec article composé
        ("croissant", "les croissants"),  # Pluriel
        ("fromage", "le fromage."),       # Avec ponctuation
        ("chocolat", "chocolate"),        # Faute de frappe
        ("paris", "Paris"),               # Casse différente
        ("eau", "de l'eau"),             # Avec article contracté
        ("pomme", "une pommes"),          # Faute de grammaire
        ("soleil", "lune"),              # Complètement différent
        ("café", "un café au lait"),     # Réponse plus longue
    ]
    
    for expected, given in test_cases:
        test_similarity(expected, given)

"""Routage d'intention de l'agent d'investigation (P0 — réponse hors-sujet).

Bug : une question factuelle de DÉNOMBREMENT préfixée de « Analyse les données »
(« Analyse les données et dis-moi COMBIEN de clients ») était routée vers
l'agent d'investigation CAUSALE, qui répondait une tendance fabriquée (évolution
du CA, attribution « Femmes 90 % ») sans aucun rapport avec la demande.

Invariant verrouillé : `should_investigate` ne déclenche une enquête causale que
pour une VRAIE question analytique ; toute demande factuelle (combien / liste /
quels sont) part au SQL direct, même préfixée d'un verbe faible (« analyse »).
"""
from __future__ import annotations

import pytest

from app.services import agent


# (question, doit_investiguer)
FACTUAL = [
    "Analyse les données et dis moi combien j'ai de client, combien j'ai de magasins",
    "combien de clients ai-je ?",
    "nombre de magasins",
    "Analyse les données et liste mes magasins",
    "quels sont mes magasins ?",
    "how many customers do I have",
]

CAUSAL = [
    "Pourquoi les ventes baissent ?",
    "Analyse la tendance du chiffre d'affaires",
    "Comprendre la répartition des ventes par région",  # verbe faible, pas de compte
    "Analyse les segments clients",                      # analytique ouvert
    "Qu'est-ce qui explique le recul en PACA ?",
]


@pytest.mark.parametrize("q", FACTUAL)
def test_factual_questions_are_not_investigated(q):
    # Une question de dénombrement/liste ne part JAMAIS en investigation causale.
    assert agent.should_investigate(q) is False


@pytest.mark.parametrize("q", CAUSAL)
def test_causal_questions_are_investigated(q):
    assert agent.should_investigate(q) is True


def test_analyse_prefix_does_not_hijack_a_count_question():
    """Cœur du P0 : le préfixe « Analyse les données » ne transforme pas une
    question « combien » en enquête causale."""
    plain = "combien j'ai de clients, combien de magasins"
    prefixed = "Analyse les données et dis moi " + plain
    assert agent.should_investigate(plain) is False
    assert agent.should_investigate(prefixed) is False

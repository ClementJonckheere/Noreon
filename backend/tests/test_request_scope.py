"""Honnêteté du moteur (Phase 1) : une demande hors répertoire est REFUSÉE,
jamais remplacée en douce par une tendance de chiffre d'affaires par défaut.

On verrouille : plusieurs formulations complexes (RFM, segmentation, cohortes,
corrélation, croisement de dimensions, tranches dérivées) ne « retombent » pas
vers l'analyse par défaut ; la couverture de la demande vaut alors 0 ; et le
message reste métier (jamais de détail technique type « hors-ligne »).
"""
from __future__ import annotations

import pytest

from app.services import request_scope as rs


# Formulations COMPLEXES — doivent être refusées (aucune substitution).
REFUSE = [
    # le cas exact rapporté (apostrophe typographique incluse)
    "Fait moi une analyse sur les clients qui achete nos produits, donc Un score "
    "de segmentation RFM. Quel produits / type de produits et achetée par quelle tranche d’âge",
    # reformulations SANS le mot « RFM »
    "Segmente mes clients par valeur d'achat",
    "Fais une analyse de cohortes des inscriptions",
    "Quelle est la corrélation entre l'âge et le panier moyen",
    "Répartis le chiffre d'affaires par produit et par région",
    "ventile les ventes par produit et par ville",
    "clustering des clients selon leur comportement",
    "prévision des ventes pour le trimestre prochain",
]

# Demandes DANS le répertoire — ne doivent jamais être refusées. Inclut les
# pièges « nom vs opération » : « le churn » (mesure) et « par segment »
# (dimension existante) sont des analyses normales, pas des méthodes.
PASS = [
    "combien de clients ai-je, combien de magasins",
    "Analyse les données et dis moi combien j'ai de clients",
    "chiffre d'affaires par mois",
    "Pourquoi les ventes baissent ?",
    "Pourquoi le churn augmente-t-il ?",          # « churn » = mesure, pas un modèle
    "Montre l'attrition par segment de clientèle",  # métrique × UNE dimension
    "combien de clients par ville",
    "évolution du chiffre d'affaires",
    "quels sont mes magasins ?",
]


@pytest.mark.parametrize("q", REFUSE)
def test_out_of_scope_requests_are_refused_with_zero_coverage(q):
    s = rs.assess(q)
    assert s.refuse is True
    # Couverture de la DEMANDE = 0 : rien de traité, jamais 100 % hors sujet.
    assert s.coverage == 0.0
    # Au moins un objectif explicitement marqué hors répertoire.
    assert s.objectives and all(o.status == "unsupported" for o in s.objectives)


@pytest.mark.parametrize("q", PASS)
def test_supported_requests_pass_through(q):
    s = rs.assess(q)
    assert s.refuse is False
    assert s.coverage == 1.0


def test_rfm_request_lists_its_real_objectives():
    q = ("Un score de segmentation RFM. Quel produits par quelle tranche d’âge")
    s = rs.assess(q)
    labels = [o.label for o in s.objectives]
    assert "une segmentation RFM" in labels
    # la tranche dérivée est citée avec les mots de l'utilisateur
    assert any("tranche" in l for l in labels)
    # RFM ne doit PAS dupliquer « segmentation » / « scoring » génériques
    assert "une segmentation" not in labels and "un scoring" not in labels


def test_refusal_message_is_business_language_not_technical():
    s = rs.assess("segmentation RFM par tranche d'âge")
    m = s.message.lower()
    assert "je préfère ne pas substituer" in m
    # jamais de vocabulaire technique interne
    for banned in ("offline", "hors-ligne", "hors ligne", "heuristi", "provider", "llm", "sql"):
        assert banned not in m


def test_multi_objective_request_keeps_all_objectives():
    # Quatre demandes distinctes hors répertoire → les quatre sont conservées.
    q = ("Fais une segmentation RFM, une analyse de cohortes, "
         "une corrélation âge/panier et une prévision des ventes")
    s = rs.assess(q)
    labels = " | ".join(o.label for o in s.objectives)
    assert "RFM" in labels
    assert "cohortes" in labels
    assert "corrélation" in labels
    assert "prévision" in labels

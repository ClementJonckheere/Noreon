"""Phase 2 — C3 : jeu d'ÉVALUATION du planificateur (partagé C1↔C3).

Chaque cas décrit une DEMANDE et les attentes au niveau INTERPRÉTATION (nombre
d'objectifs, types, arêtes de dépendance, termes non résolus) ainsi que le modèle
ATTENDU en sortie du routeur (`simple_eligible` → gpt-oss-20b, sinon gpt-oss-120b).
Utilisé pour tester les validateurs (C1), le routeur et le benchmark (C3).

DOMAINE-AGNOSTIQUE : les attentes portent sur la STRUCTURE, jamais sur des noms
de tables/colonnes.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    min_goals: int
    expect_types: frozenset            # types d'objectifs attendus (au moins)
    depends_on_edges: tuple[tuple[str, str], ...] = ()   # (enfant, parent) attendues
    expect_unresolved_roles: frozenset = field(default_factory=frozenset)
    expect_clarification: bool = False
    # Éligibilité au modèle SIMPLE (gpt-oss-20b) : un seul objectif count/aggregate/
    # ranking, sans méthode, dépendance, ambiguïté ni croisement. Tout doute → 120b.
    simple_eligible: bool = False
    note: str = ""


CASES: list[EvalCase] = [
    # ---- Complexes (gpt-oss-120b) ----
    EvalCase(
        id="rfm_full",
        question=("Fais une analyse des clients qui achètent nos produits : un score de "
                  "segmentation RFM, quels produits par segment, et par quelle tranche d'âge"),
        min_goals=3,
        expect_types=frozenset({"segmentation", "affinity", "distribution"}),
        depends_on_edges=(("affinity", "segmentation"),),
        expect_unresolved_roles=frozenset({"dimension"}),
        note="cas de référence RFM",
    ),
    EvalCase(
        id="rfm_no_acronym",
        question=("Segmente mes clients selon leur valeur et regarde quels types de "
                  "produits chaque segment achète"),
        min_goals=2,
        expect_types=frozenset({"segmentation", "affinity"}),
        depends_on_edges=(("affinity", "segmentation"),),
        note="RFM reconnu sans le sigle",
    ),
    EvalCase(
        id="four_objectives",
        question=("Fais une segmentation RFM, une analyse de cohortes des inscriptions, "
                  "la corrélation entre ancienneté et valeur, et un classement des produits"),
        min_goals=4,
        expect_types=frozenset({"segmentation", "cohort", "correlation", "ranking"}),
        note="quatre objectifs conservés",
    ),
    EvalCase(
        id="ambiguity_ttc",
        question="Analyse le chiffre d'affaires par segment (HT ou TTC ?)",
        min_goals=1,
        expect_types=frozenset({"attribution"}),
        expect_clarification=True,
        note="ambiguïté de mesure → clarification (jamais 20b)",
    ),
    EvalCase(
        id="age_absent",
        question="Répartis mes clients par tranche d'âge",
        min_goals=1,
        expect_types=frozenset({"distribution"}),
        expect_unresolved_roles=frozenset({"dimension"}),
        note="dimension âge absente → terme non résolu, pas de ref fantôme",
    ),
    EvalCase(
        id="cross_two_dims",
        question="Répartis le chiffre d'affaires par produit et par région",
        min_goals=1,
        expect_types=frozenset({"attribution"}),
        note="croisement 2 dimensions → complexe",
    ),
    EvalCase(
        id="correlation",
        question="Quelle est la corrélation entre l'ancienneté du client et son panier moyen",
        min_goals=1,
        expect_types=frozenset({"correlation"}),
        note="méthode statistique → complexe",
    ),
    EvalCase(
        id="trend_causal",
        question="Pourquoi le chiffre d'affaires baisse-t-il depuis trois mois ?",
        min_goals=1,
        expect_types=frozenset({"attribution"}),
        note="diagnostic causal → complexe",
    ),
    EvalCase(
        id="trend_not_allowed",
        question="Montre l'évolution du chiffre d'affaires par mois",
        min_goals=1,
        expect_types=frozenset({"trend"}),
        note="tendance = hors allowlist 20b (types autorisés : count/aggregate/ranking)",
    ),

    # ---- Simples (gpt-oss-20b éligible) ----
    EvalCase(
        id="count_clients",
        question="Combien de clients ai-je ?",
        min_goals=1, expect_types=frozenset({"count"}),
        simple_eligible=True, note="dénombrement simple",
    ),
    EvalCase(
        id="count_orders",
        question="Nombre de commandes au total",
        min_goals=1, expect_types=frozenset({"count"}),
        simple_eligible=True,
    ),
    EvalCase(
        id="aggregate_revenue",
        question="Chiffre d'affaires total",
        min_goals=1, expect_types=frozenset({"aggregate"}),
        simple_eligible=True,
    ),
    EvalCase(
        id="ranking_products",
        question="Classement des produits par montant vendu",
        min_goals=1, expect_types=frozenset({"ranking"}),
        simple_eligible=True, note="top/classement simple",
    ),
    EvalCase(
        id="count_by_one_dim",
        question="Combien de clients par ville",
        min_goals=1, expect_types=frozenset({"count"}),
        simple_eligible=True, note="count + 1 dimension même table (pas de jointure)",
    ),
    EvalCase(
        id="avg_basket",
        question="Panier moyen",
        min_goals=1, expect_types=frozenset({"aggregate"}),
        simple_eligible=True,
    ),
]

CASES_BY_ID = {c.id: c for c in CASES}

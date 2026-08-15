"""Phase 2 — C1 : jeu d'ÉVALUATION du planificateur (partagé C1↔C3).

Chaque cas décrit une DEMANDE et les attentes au niveau INTERPRÉTATION (nombre
d'objectifs, types, arêtes de dépendance, termes non résolus). Utilisé :
- en C1 pour tester les validateurs de contrat sur des interprétations écrites à
  la main ;
- en C3 pour le benchmark comparatif des modèles (seuils éliminatoires).

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
    note: str = ""


CASES: list[EvalCase] = [
    EvalCase(
        id="rfm_full",
        question=("Fais une analyse des clients qui achètent nos produits : un score de "
                  "segmentation RFM, quels produits par segment, et par quelle tranche d'âge"),
        min_goals=3,
        expect_types=frozenset({"segmentation", "affinity", "distribution"}),
        depends_on_edges=(("affinity", "segmentation"),),   # l'affinité produit ⇐ segments RFM
        expect_unresolved_roles=frozenset({"dimension"}),   # « tranche d'âge » si absente
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
        note="ambiguïté de mesure → clarification",
    ),
    EvalCase(
        id="age_absent",
        question="Répartis mes clients par tranche d'âge",
        min_goals=1,
        expect_types=frozenset({"distribution"}),
        expect_unresolved_roles=frozenset({"dimension"}),
        note="dimension âge absente → terme non résolu, pas de ref fantôme",
    ),
]

CASES_BY_ID = {c.id: c for c in CASES}

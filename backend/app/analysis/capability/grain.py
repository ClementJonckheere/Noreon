"""Phase 2 — C6 : grain, cardinalités et FANOUT (primitives de 1er ordre).

Le fanout est un CALCUL par MULTIPLICITÉ (#1), pas un label. Une jointure valide
n'est PAS une agrégation sûre : le rôle de ce module est d'empêcher un résultat
plausible mais mathématiquement faux (double comptage). Une pré-agrégation
PROUVÉE sûre n'est pas une réserve (#2). La semi-additivité est explicite (#3).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.analysis.capability.model import (
    ADD_NON,
    ADD_SEMI,
    MANY_TO_MANY,
    MANY_TO_ONE,
    ONE_TO_MANY,
    ONE_TO_ONE,
    S_AVAILABLE,
    S_RESERVE,
    S_UNRESOLVED,
    STRAT_COUNT_DISTINCT,
    STRAT_NONE,
    STRAT_PRE_AGG,
    STRAT_SEMI_ADDITIVE,
    Measure,
)

_FANOUT = frozenset({ONE_TO_MANY, MANY_TO_MANY})


def step_multiplies(cardinality: str) -> bool:
    """La traversée multiplie-t-elle le flux entrant ? Vrai ssi le côté « to »
    est « many » (1→n ou n→n). Un n→1 ou 1→1 ne multiplie pas."""
    return cardinality in _FANOUT


def overall_traversal(cardinalities: list[str]) -> str:
    """Cardinalité de traversée globale (pour le champ `grain.traversal`)."""
    if not cardinalities:
        return ONE_TO_ONE
    if MANY_TO_MANY in cardinalities:
        return MANY_TO_MANY
    if ONE_TO_MANY in cardinalities:
        return ONE_TO_MANY
    if MANY_TO_ONE in cardinalities:
        return MANY_TO_ONE
    return ONE_TO_ONE


@dataclass
class GrainAnalysis:
    creates_row_multiplication: bool
    requires_pre_aggregation: bool
    strategy: str
    state: str                       # available | available_with_reserve | unresolved
    reason_code: str | None = None
    reason_detail: str | None = None
    reserve: dict | None = None


def analyze_measure(measure: Measure | None, cardinalities: list[str], *,
                    agg_dims: frozenset[str] = frozenset(), is_count: bool = False) -> GrainAnalysis:
    """Décide la stratégie d'agrégation SÛRE d'une mesure le long d'un chemin.

    - Pas de fanout → agrégation directe, `available`.
    - Fanout + dénombrement d'entités → `count_distinct` sur la clé de grain, `available`.
    - Fanout + mesure au grain CONNU, additive → `pre_aggregation`, `available` (#2).
    - Fanout + semi-additive sur axe non-additif → `semi_additive`, `reserve` (#3).
    - Fanout + non-additive ou grain INCONNU → `unresolved` (jamais une somme fausse)."""
    fanout = any(step_multiplies(c) for c in cardinalities)

    # Non-additive (ratio, taux…) : jamais sommable — AVEC OU SANS fanout (#3).
    if measure is not None and measure.additivity == ADD_NON and not is_count:
        return GrainAnalysis(fanout, fanout, STRAT_NONE, S_UNRESOLVED,
                             reason_code="non_additive_measure",
                             reason_detail="mesure non-additive : ne peut être sommée, à recomposer")

    # Semi-additive sur un axe non-additif : unsafe AVEC OU SANS fanout (#3).
    if measure is not None and measure.additivity == ADD_SEMI and (agg_dims & measure.non_additive_dims):
        offending = sorted(agg_dims & measure.non_additive_dims)
        return GrainAnalysis(fanout, fanout, STRAT_SEMI_ADDITIVE, S_RESERVE,
                             reason_code="semi_additive_axis",
                             reason_detail=f"axe non-additif pour une mesure semi-additive : {offending}",
                             reserve={"type": "semi_additive", "non_additive_dims": offending})

    if not fanout:
        return GrainAnalysis(False, False, STRAT_NONE, S_AVAILABLE)

    if is_count:
        return GrainAnalysis(True, True, STRAT_COUNT_DISTINCT, S_AVAILABLE,
                             reason_code="count_distinct_under_fanout")

    if measure is None or not measure.home_entity:
        return GrainAnalysis(True, True, STRAT_NONE, S_UNRESOLVED,
                             reason_code="grain_unknown_under_fanout",
                             reason_detail="grain de la mesure inconnu sous fanout — somme non sûre")

    # Additive (ou semi sur axes additifs) : la pré-agrégation est PROUVÉE sûre (#2).
    return GrainAnalysis(True, True, STRAT_PRE_AGG, S_AVAILABLE,
                         reason_code="pre_aggregation_safe")

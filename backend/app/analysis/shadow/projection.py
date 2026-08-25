"""Phase 2 — C5 : projections comparables (LLM ↔ fallback).

Le comparateur ne travaille PAS sur l'égalité JSON, mais sur une projection
structurée. Règle d'or (correctif utilisateur #5) : **`unknown` ≠ `empty`**.
Un champ à `None` = « non exprimé / non comparable » ; un ensemble vide = « zéro
explicite ». Cette distinction est PORTÉE DANS LES DONNÉES (sérialisation), pas
seulement dans la tête du comparateur, sinon on fabrique de faux accords.
"""
from __future__ import annotations

from dataclasses import dataclass

# Version de la LOGIQUE de projection (mapping plan→facettes). Persistée en
# télémétrie pour distinguer une dérive « projection » des autres.
PROJECTION_VERSION = "1.0"


def _dump(value):
    """Sérialise un champ de facette : None reste null (unknown), un ensemble
    devient une liste triée (empty → [], sémantiquement distinct de null)."""
    if value is None:
        return None
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    return value


@dataclass(frozen=True)
class ComparableProjection:
    """Facettes normalisées. `None` = inconnu/non exprimé (NOT_COMPARABLE) ;
    `frozenset()`/`0` = zéro explicite. Ne jamais confondre les deux."""
    source: str                                   # "llm" | "fallback"
    primary_goal_type: str | None = None
    goal_types: frozenset[str] | None = None
    goal_count: int | None = None
    dependency_edges: frozenset[tuple[str, str]] | None = None   # {(child, parent)}
    unresolved_roles: frozenset[str] | None = None
    # PROVISOIRE (correctif #3) : signature de capabilities déduite
    # heuristiquement. INFORMATIVE uniquement jusqu'à C6 — jamais matérielle.
    required_capabilities: frozenset[str] | None = None
    capabilities_provisional: bool = True

    def to_json(self) -> dict:
        return {
            "source": self.source,
            "primary_goal_type": _dump(self.primary_goal_type),
            "goal_types": _dump(self.goal_types),
            "goal_count": _dump(self.goal_count),
            "dependency_edges": (None if self.dependency_edges is None
                                 else sorted([list(e) for e in self.dependency_edges])),
            "unresolved_roles": _dump(self.unresolved_roles),
            "required_capabilities": _dump(self.required_capabilities),
            "capabilities_provisional": self.capabilities_provisional,
            "projection_version": PROJECTION_VERSION,
        }


def project_llm(interp) -> ComparableProjection:
    """Projection du plan LLM (`Interpretation`). Toutes les facettes sont
    EXPRIMÉES par le contrat → jamais `None` ici (un plan sans dépendance a
    `dependency_edges = frozenset()`, pas `None`)."""
    goals = list(interp.goals)
    primary = min(goals, key=lambda g: g.priority)
    edges = frozenset(
        (g.id, dep) for g in goals for dep in (g.depends_on or ()))
    unresolved = frozenset(
        t.get("role") for t in interp.unresolved_terms if isinstance(t, dict) and t.get("role"))
    caps: set[str] = set()
    for g in goals:
        caps.add(f"goal:{g.type}")
        dims = g.raw.get("dimensions") or []
        if dims:
            caps.add("dimensions")
        if len(dims) > 1:
            caps.add("cross_dimension")
        if g.raw.get("method"):
            caps.add(f"method:{(g.raw['method'] or {}).get('name', '?')}")
        if g.depends_on:
            caps.add("multi_goal")
    return ComparableProjection(
        source="llm",
        primary_goal_type=primary.type,
        goal_types=frozenset(g.type for g in goals),
        goal_count=len(goals),
        dependency_edges=edges,
        unresolved_roles=unresolved,
        required_capabilities=frozenset(caps),
        capabilities_provisional=True,
    )


# Mapping PROVISOIRE fallback → type d'objectif principal. Le fallback n'est PAS
# une vérité terrain et n'expose pas de plan : la plupart des facettes restent
# `None` (unknown), volontairement — pas `frozenset()`.
_FALLBACK_GOAL_HINTS = {
    "trend": "trend", "tendance": "trend", "evolution": "trend",
    "count": "count", "denombrement": "count",
    "aggregate": "aggregate", "somme": "aggregate", "moyenne": "aggregate",
    "ranking": "ranking", "classement": "ranking", "top": "ranking",
    "attribution": "attribution", "distribution": "distribution",
    "segmentation": "segmentation", "cohort": "cohort", "correlation": "correlation",
    "affinity": "affinity",
}


def _fallback_primary_goal_type(view: dict) -> str | None:
    """Best-effort : dérive le type d'analyse du fallback depuis sa réponse.
    Renvoie `None` (unknown) dès que ce n'est pas explicite — jamais un défaut."""
    if not isinstance(view, dict):
        return None
    if view.get("status") in {"out_of_scope", "unanswerable", "no_schema", "blocked", "error"}:
        return None                                # le fallback n'a pas conclu → unknown
    analysis = view.get("analysis")
    if isinstance(analysis, dict):
        for key in ("goal_type", "kind", "type"):
            v = analysis.get(key)
            if isinstance(v, str) and v.lower() in _FALLBACK_GOAL_HINTS:
                return _FALLBACK_GOAL_HINTS[v.lower()]
    hint = view.get("goal_type_hint")
    if isinstance(hint, str) and hint.lower() in _FALLBACK_GOAL_HINTS:
        return _FALLBACK_GOAL_HINTS[hint.lower()]
    return None


def project_fallback(view: dict) -> ComparableProjection:
    """Projection best-effort du fallback. Il n'énumère pas d'objectifs ni de DAG
    en termes de planner → ces facettes restent `None` (NOT_COMPARABLE), ce qui
    empêche tout faux accord. Seul `primary_goal_type` est parfois dérivable."""
    return ComparableProjection(
        source="fallback",
        primary_goal_type=_fallback_primary_goal_type(view),
        goal_types=None,               # unknown, PAS frozenset()
        goal_count=None,
        dependency_edges=None,
        unresolved_roles=None,
        required_capabilities=None,
        capabilities_provisional=True,
    )

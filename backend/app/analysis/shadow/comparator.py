"""Phase 2 — C5 : comparateur structuré LLM ↔ fallback.

Le fallback n'est PAS une vérité terrain : une différence est une `divergence`,
jamais une « erreur modèle ». La comparaison inspecte des FACETTES (objectif
principal, types, nombre, graphe de dépendances, unresolved, capabilities), pas
l'égalité JSON. `unknown` (None) n'entre jamais en accord ni en désaccord.

Rappels des correctifs utilisateur :
- #3 : `required_capabilities` est INFORMATIF seulement (jamais matériel avant C6).
- #6 : les équivalences de types sont une RÈGLE VERSIONNÉE, pas une vérité implicite.
- renommage : `comparison_outcome` (les erreurs LLM/fallback ne sont pas des divergences).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.analysis.shadow.projection import ComparableProjection, _dump

# Version de la LOGIQUE de comparaison.
COMPARATOR_VERSION = "1.0"

# Règle d'équivalence de types VERSIONNÉE (correctif #6). Ces classes disent que
# deux types sont interchangeables pour juger l'objectif principal — décision
# tracée, pas codée en dur comme vérité universelle.
TYPE_EQUIVALENCE_VERSION = "1.0"
TYPE_EQUIVALENCES: tuple[frozenset[str], ...] = (
    frozenset({"count", "aggregate"}),
)

# Résultats de comparaison. Les états d'erreur ne sont PAS des divergences.
IDENTICAL = "identical"
EQUIVALENT = "equivalent"
MATERIAL_DIVERGENCE = "material_divergence"
NOT_COMPARABLE = "not_comparable"        # aucune facette matérielle comparable (unknown≠empty)
LLM_ERROR = "llm_error"                  # le LLM n'a pas produit de plan valide (détail: llm_status)
FALLBACK_ERROR = "fallback_error"        # le fallback a échoué

# Facettes MATÉRIELLES en C5 (capabilities exclues → informatives jusqu'à C6).
_MATERIAL = ("primary_goal_type", "goal_types", "dependency_edges", "unresolved_roles")


def _class_of(t: str) -> str:
    for cls in TYPE_EQUIVALENCES:
        if t in cls:
            return "|".join(sorted(cls))
    return t


def _canon_types(s: frozenset[str]) -> frozenset[str]:
    return frozenset(_class_of(t) for t in s)


def _facet(llm_val, fb_val, agree_fn) -> dict:
    """None d'un côté → `not_comparable` (jamais accord ni désaccord)."""
    if llm_val is None or fb_val is None:
        return {"llm": _dump(llm_val), "fallback": _dump(fb_val), "state": "not_comparable"}
    state = "agree" if agree_fn(llm_val, fb_val) else "disagree"
    return {"llm": _dump(llm_val), "fallback": _dump(fb_val), "state": state}


@dataclass(frozen=True)
class ShadowComparison:
    outcome: str
    facets: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "outcome": self.outcome,
            "facets": self.facets,
            "comparator_version": COMPARATOR_VERSION,
            "type_equivalence_version": TYPE_EQUIVALENCE_VERSION,
        }


def compare(llm: ComparableProjection | None, fallback: ComparableProjection | None,
            *, llm_status: str, fallback_status: str) -> ShadowComparison:
    """Classe le résultat de comparaison. Priorité aux états d'erreur (non-divergences)."""
    if llm_status != "ok" or llm is None:
        return ShadowComparison(LLM_ERROR, {"llm_status": llm_status})
    if fallback_status != "ok" or fallback is None:
        return ShadowComparison(FALLBACK_ERROR, {"fallback_status": fallback_status})

    facets = {
        "primary_goal_type": _facet(llm.primary_goal_type, fallback.primary_goal_type,
                                    lambda a, b: _class_of(a) == _class_of(b)),
        "goal_types": _facet(llm.goal_types, fallback.goal_types,
                             lambda a, b: _canon_types(a) == _canon_types(b)),
        "goal_count": _facet(llm.goal_count, fallback.goal_count, lambda a, b: a == b),
        "dependency_edges": _facet(llm.dependency_edges, fallback.dependency_edges,
                                   lambda a, b: a == b),
        "unresolved_roles": _facet(llm.unresolved_roles, fallback.unresolved_roles,
                                   lambda a, b: a == b),
        # INFORMATIF seulement (jamais matériel en C5) :
        "required_capabilities": {
            **_facet(llm.required_capabilities, fallback.required_capabilities, lambda a, b: a == b),
            "material": False, "provisional": True},
    }

    material_states = [facets[f]["state"] for f in _MATERIAL]
    if "disagree" in material_states:
        return ShadowComparison(MATERIAL_DIVERGENCE, facets)
    if "agree" not in material_states:
        # aucune facette matérielle comparable (ex. fallback n'expose rien)
        return ShadowComparison(NOT_COMPARABLE, facets)

    # Au moins une facette matérielle comparable, aucune en désaccord.
    strong = ("primary_goal_type", "goal_types", "goal_count",
              "dependency_edges", "unresolved_roles")
    if all(facets[f]["state"] == "agree" for f in strong):
        return ShadowComparison(IDENTICAL, facets)
    return ShadowComparison(EQUIVALENT, facets)

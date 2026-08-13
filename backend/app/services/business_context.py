"""Contrat GÉNÉRIQUE de contexte d'entreprise — primitive du produit.

Un `BusinessContext` décrit une organisation SANS présumer d'un domaine : acteurs,
concepts, entités, responsabilités, conventions, capacités. **Tout est optionnel.**
Noreon doit fonctionner parfaitement avec `actors = []` et `responsibilities = []` —
un entrepreneur solo qui a seulement connecté ses données obtient quand même :

    « Le recul se concentre sur… »
    « Une action possible consiste à… »
    « Cette action pourrait être mesurée par… »

Les rôles et responsabilités ENRICHISSENT les recommandations ; ils ne sont jamais
une condition de fonctionnement. Chaque élément porte une ORIGINE :

    inferred  — inféré depuis les données / le schéma / les usages
    declared  — renseigné par l'utilisateur
    validated — confirmé par un humain

Aucun vocabulaire métier (magasin, région, gamme, rôle…) ne vit ici : il appartient
aux fixtures d'un contexte déclaré (voir `app/fixtures/demo_retail.py`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Origin(str, Enum):
    INFERRED = "inferred"
    DECLARED = "declared"
    VALIDATED = "validated"


@dataclass
class Actor:
    id: str
    label: str
    source: str = Origin.DECLARED.value
    confidence: float = 1.0
    status: str = "declared"


@dataclass
class ConceptRef:
    id: str
    label: str
    source: str = Origin.INFERRED.value
    confidence: float = 0.5
    status: str = "candidate"


@dataclass
class EntityRef:
    id: str
    label: str
    source: str = Origin.INFERRED.value
    confidence: float = 0.5
    status: str = "candidate"


@dataclass
class BusinessConvention:
    id: str
    label: str
    source: str = Origin.DECLARED.value


@dataclass
class BusinessCapability:
    id: str
    label: str
    source: str = Origin.INFERRED.value


@dataclass
class ResponsibilityMatcher:
    """Mécanisme de détection GÉNÉRIQUE : les ENSEMBLES de valeurs et le motif de nom
    sont fournis par le contexte, jamais codés dans le moteur. Détecter par la valeur
    d'abord rend le routage robuste aux colonnes opaques (un axe nommé « a3 » reste
    reconnu si ses valeurs le trahissent)."""
    value_set: frozenset[str] = field(default_factory=frozenset)
    value_tokens: tuple[str, ...] = ()          # sous-chaînes distinctives
    name_pattern: str | None = None

    def matches_by_value(self, values: list[str]) -> bool:
        low = [str(v).strip().lower() for v in values if v is not None and str(v).strip()]
        if not low:
            return False
        if self.value_set and any(v in self.value_set for v in low):
            return True
        if self.value_tokens and any(any(tok in v for tok in self.value_tokens) for v in low):
            return True
        return False

    def matches_by_name(self, dimension_label: str) -> bool:
        return bool(self.name_pattern and re.search(self.name_pattern, (dimension_label or "").lower()))


@dataclass
class Responsibility:
    """Rattache un CONCEPT à un décideur (si l'organisation est connue) et à une
    action-type. `actor_label = None` ⇒ concept reconnu mais sans responsable (aucune
    personnalisation) ; `action_template = ""` ⇒ concept reconnu mais sans action
    dédiée (aucune décision émise, ni générique)."""
    concept_key: str
    concept_label: str
    actor_label: str | None = None
    action_template: str = ""
    justification_template: str = ""
    effort: str = "Moyen"
    matcher: ResponsibilityMatcher = field(default_factory=ResponsibilityMatcher)
    source: str = Origin.DECLARED.value
    confidence: float = 1.0
    status: str = "declared"


@dataclass
class BusinessContext:
    actors: list[Actor] = field(default_factory=list)
    concepts: list[ConceptRef] = field(default_factory=list)
    entities: list[EntityRef] = field(default_factory=list)
    responsibilities: list[Responsibility] = field(default_factory=list)
    conventions: list[BusinessConvention] = field(default_factory=list)
    capabilities: list[BusinessCapability] = field(default_factory=list)

    def resolve_responsibility(self, dimension_label: str, segment: str | None = None,
                               samples: list[str] | None = None) -> Responsibility | None:
        """Un Finding sur un axe → une Responsibility SI le contexte en connaît une.
        Valeurs d'abord (toutes responsabilités), puis nom. Sans contexte : None."""
        values = ([segment] if segment else []) + list(samples or [])
        for r in self.responsibilities:
            if r.matcher.matches_by_value(values):
                return r
        for r in self.responsibilities:
            if r.matcher.matches_by_name(dimension_label):
                return r
        return None

    def actor(self, actor_id: str) -> str | None:
        for a in self.actors:
            if a.id == actor_id:
                return a.label
        return None


# Contexte VIDE = organisation inconnue → recommandations 100 % génériques.
EMPTY = BusinessContext()


def resolve_for(db, connection) -> BusinessContext:
    """Contexte DÉCLARÉ du tenant (fixture nommée), sinon vide (générique). Simple
    câblage d'une fixture déclarée — aucune logique métier, aucun couplage retail
    dans le moteur : c'est le tenant qui a *déclaré* utiliser telle fixture."""
    from app.models.tenant import TenantSettings

    st = db.get(TenantSettings, connection.tenant_id) if connection is not None else None
    name = (st.preferences or {}).get("business_context") if st else None
    if name == "demo_retail":
        from app.fixtures import demo_retail
        return demo_retail.context()
    return EMPTY

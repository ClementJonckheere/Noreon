"""Phase 2 — C6 : modèle canonique du CapabilityResolver.

Aucun nom métier : uniquement des refs sémantiques (`concept:/metric:/dimension:`)
et des primitives génériques (grain, multiplicité, additivité). Fonctionne à
l'identique pour Retail, SaaS ou une base solo à une seule table.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CAPABILITY_RESOLVER_VERSION = "1.0"

# Cardinalités canoniques (alignées sur le contrat resolved_plan).
MANY_TO_ONE = "many_to_one"
ONE_TO_MANY = "one_to_many"
ONE_TO_ONE = "one_to_one"
MANY_TO_MANY = "many_to_many"
CARDINALITIES = frozenset({MANY_TO_ONE, ONE_TO_MANY, ONE_TO_ONE, MANY_TO_MANY})

# Une traversée MULTIPLIE le flux entrant ssi le côté « to » est « many »
# (correction #1 : fanout formalisé par MULTIPLICITÉ, pas par label).
_FANOUT_STEP = frozenset({ONE_TO_MANY, MANY_TO_MANY})

# Additivité d'une mesure (correction #3 : semi-additivité explicite).
ADD_FULL, ADD_SEMI, ADD_NON = "full", "semi", "non"

# États de capability (par exigence). `available` est DISTINCT de l'accès (#5).
S_AVAILABLE = "available"
S_RESERVE = "available_with_reserve"
S_UNRESOLVED = "unresolved"
S_BLOCKED = "blocked"

# Classes de cause. `blocked` peut être access OU quality-hard-stop (#7),
# jamais confondu avec `unresolved` (manque de structure).
CAUSE_CAPABILITY = "capability"
CAUSE_QUALITY = "quality"
CAUSE_ACCESS = "access"

# Stratégies anti-double-comptage (décidées ici, exécutées par le compiler).
STRAT_NONE = "none"
STRAT_PRE_AGG = "pre_aggregation"
STRAT_COUNT_DISTINCT = "count_distinct"
STRAT_SEMI_ADDITIVE = "semi_additive"


@dataclass(frozen=True)
class Entity:
    ref: str
    grain_keys: tuple[str, ...]                 # clés d'unicité (le GRAIN)
    physical: str | None = None                 # table physique


@dataclass(frozen=True)
class Measure:
    ref: str
    home_entity: str                            # entité au grain de laquelle la mesure est définie
    additivity: str = ADD_FULL                  # full | semi | non
    non_additive_dims: frozenset[str] = field(default_factory=frozenset)  # axes non sommables (semi)
    physical: str | None = None


@dataclass(frozen=True)
class Dimension:
    ref: str
    home_entity: str
    physical: str | None = None


_INVERSE_CARD = {MANY_TO_ONE: ONE_TO_MANY, ONE_TO_MANY: MANY_TO_ONE,
                 ONE_TO_ONE: ONE_TO_ONE, MANY_TO_MANY: MANY_TO_MANY}


@dataclass(frozen=True)
class Relation:
    id: int
    from_entity: str
    to_entity: str
    cardinality: str                            # canonique (many_to_one, …) DANS le sens from→to
    from_key: str | None = None                 # clé physique "table.col" côté from
    to_key: str | None = None                   # clé physique "table.col" côté to
    status: str = "candidate"                   # candidate|needs_validation|validated|archived|rejected
    origin: str = "inferred"                    # constraint|inferred|declared
    coverage: float | None = None
    target_uniqueness: float | None = None

    @property
    def inverse_cardinality(self) -> str:
        return _INVERSE_CARD.get(self.cardinality, self.cardinality)

    @property
    def is_system_validated(self) -> bool:
        # Correction #6 : une FK physique confirmée (origin=constraint) est
        # AUTORITAIRE — utilisable sans validation humaine. L'inféré, non.
        return self.status == "validated" or self.origin == "constraint"


@dataclass(frozen=True)
class ResolutionPolicy:
    staleness_mode: str = "reserve"             # reserve | strict (hard-stop qualité)
    min_coverage: float = 0.0
    min_target_uniqueness: float = 0.0
    quality_hard_stop: float = 0.0              # score qualité < seuil ⇒ blocked(quality)
    max_path_depth: int = 5


@dataclass(frozen=True)
class ResolutionContext:
    """Tout est optionnel et porte une origine `inferred|declared|validated`.
    Produit par un `CapabilityCatalogAdapter` — le resolver ne voit que du canonique."""
    entities: dict[str, Entity] = field(default_factory=dict)
    measures: dict[str, Measure] = field(default_factory=dict)
    dimensions: dict[str, Dimension] = field(default_factory=dict)
    relations: tuple[Relation, ...] = ()
    freshness: dict = field(default_factory=dict)     # ref → {stale: bool, ...}
    quality: dict = field(default_factory=dict)       # ref → score 0..1
    access: dict = field(default_factory=dict)        # {hidden: set[ref], source_reachable: bool}
    policy: ResolutionPolicy = field(default_factory=ResolutionPolicy)


@dataclass
class CapabilityRequirement:
    kind: str                                   # entity|measure|dimension|relation|grain|method
    ref: str
    capability_state: str = S_AVAILABLE         # available|reserve|unresolved (AXE capability+qualité)
    access_state: str = "granted"               # granted|blocked (AXE accès — orthogonal, #5)
    cause_class: str | None = None
    reason_code: str | None = None
    reason_detail: str | None = None
    reserve: dict | None = None
    strategy: str = STRAT_NONE
    creates_row_multiplication: bool = False    # fanout DÉTECTÉ (grain req), même si le goal est unsupported

    @property
    def state(self) -> str:
        """État EFFECTIF. L'accès est un axe distinct : blocked prime, mais on
        garde la trace que la capability était disponible (available≠access)."""
        if self.access_state == "blocked":
            return S_BLOCKED
        return self.capability_state

    def to_json(self) -> dict:
        return {
            "kind": self.kind, "ref": self.ref, "state": self.state,
            "capability_state": self.capability_state, "access_state": self.access_state,
            "cause_class": self.cause_class, "reason_code": self.reason_code,
            "reason_detail": self.reason_detail, "reserve": self.reserve, "strategy": self.strategy,
        }


@dataclass
class GoalResolution:
    goal_id: str
    status: str                                 # SUPPORTED|PARTIAL|UNSUPPORTED|NEEDS_CLARIFICATION
    requirements: list[CapabilityRequirement] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"goal_id": self.goal_id, "status": self.status,
                "requirements": [r.to_json() for r in self.requirements]}


@dataclass
class CapabilityResolution:
    """Artefact RICHE (narration/coverage/shadow). Le `resolved_plan_json` en est
    dérivé et validé séparément (contrat compiler)."""
    goals: list[GoalResolution] = field(default_factory=list)
    resolver_version: str = CAPABILITY_RESOLVER_VERSION

    def to_json(self) -> dict:
        return {"resolver_version": self.resolver_version,
                "goals": [g.to_json() for g in self.goals]}

"""Phase 2 — C6 : CapabilityCatalogAdapter (#8).

Le resolver ne consomme que du `ResolutionContext` CANONIQUE. Les catalogues réels
(snapshot DB, relation_candidates, concept_definitions) ou de démo n'ont pas
toujours ce typage : l'adapter normalise. Il mappe aussi le vocabulaire de
cardinalité `n-1|1-1|1-n|n-n` (modèle relation) vers le canonique. Aucun nom métier.
"""
from __future__ import annotations

from app.analysis.capability.model import (
    ADD_FULL,
    MANY_TO_MANY,
    MANY_TO_ONE,
    ONE_TO_MANY,
    ONE_TO_ONE,
    Dimension,
    Entity,
    Measure,
    Relation,
    ResolutionContext,
    ResolutionPolicy,
)

# Vocabulaire du modèle relation_candidate → canonique.
_CARD_MAP = {
    "n-1": MANY_TO_ONE, "many_to_one": MANY_TO_ONE,
    "1-n": ONE_TO_MANY, "one_to_many": ONE_TO_MANY,
    "1-1": ONE_TO_ONE, "one_to_one": ONE_TO_ONE,
    "n-n": MANY_TO_MANY, "many_to_many": MANY_TO_MANY,
}


def normalize_cardinality(raw: str | None) -> str:
    """Normalise n'importe quel dialecte de cardinalité ; défaut PRUDENT n-n
    (le pire cas fanout) quand c'est inconnu — jamais un accord silencieux."""
    return _CARD_MAP.get((raw or "").strip().lower(), MANY_TO_MANY)


class CapabilityCatalogAdapter:
    """Base : `to_context(spec) -> ResolutionContext`. Sous-classer pour une source
    concrète (snapshot DB, fixtures de démo, etc.)."""

    def to_context(self, spec) -> ResolutionContext:  # pragma: no cover - interface
        raise NotImplementedError


class DictCatalogAdapter(CapabilityCatalogAdapter):
    """Adapter générique depuis un `spec` déclaratif (dict). Remplit les défauts
    canoniques quand une info manque, SANS inventer de structure métier."""

    def to_context(self, spec: dict) -> ResolutionContext:
        entities = {}
        for e in spec.get("entities", []):
            entities[e["ref"]] = Entity(
                ref=e["ref"], grain_keys=tuple(e.get("grain_keys") or ()),
                physical=e.get("physical"), grain_key_types=dict(e.get("grain_key_types") or {}),
                aliases=tuple(e.get("aliases") or ()))
        measures = {}
        for m in spec.get("measures", []):
            measures[m["ref"]] = Measure(
                ref=m["ref"], home_entity=m.get("home_entity", ""),
                additivity=m.get("additivity", ADD_FULL),
                non_additive_dims=frozenset(m.get("non_additive_dims") or ()),
                physical=m.get("physical"), data_type=m.get("data_type"),
                aliases=tuple(m.get("aliases") or ()))
        dimensions = {}
        for d in spec.get("dimensions", []):
            dimensions[d["ref"]] = Dimension(
                ref=d["ref"], home_entity=d.get("home_entity", ""),
                physical=d.get("physical"), data_type=d.get("data_type"),
                is_temporal=bool(d.get("is_temporal", False)),
                aliases=tuple(d.get("aliases") or ()))
        relations = tuple(
            Relation(id=int(r["id"]), from_entity=r["from_entity"], to_entity=r["to_entity"],
                     cardinality=normalize_cardinality(r.get("cardinality")),
                     from_key=r.get("from_key"), to_key=r.get("to_key"),
                     status=r.get("status", "candidate"), origin=r.get("origin", "inferred"),
                     coverage=r.get("coverage"), target_uniqueness=r.get("target_uniqueness"),
                     direction=r.get("direction", "from_to"),
                     validation_status=r.get("validation_status"),
                     evidence=r.get("evidence"),
                     provenance=tuple(r.get("provenance") or ()),
                     executable=r.get("executable"))
            for r in spec.get("relations", []))
        pol = spec.get("policy") or {}
        return ResolutionContext(
            entities=entities, measures=measures, dimensions=dimensions,
            column_roles={key: tuple(value) for key, value in (spec.get("column_roles") or {}).items()},
            relations=relations,
            freshness=spec.get("freshness") or {}, quality=spec.get("quality") or {},
            access=spec.get("access") or {},
            policy=ResolutionPolicy(
                staleness_mode=pol.get("staleness_mode", "reserve"),
                min_coverage=pol.get("min_coverage", 0.0),
                min_target_uniqueness=pol.get("min_target_uniqueness", 0.0),
                quality_hard_stop=pol.get("quality_hard_stop", 0.0),
                max_path_depth=pol.get("max_path_depth", 5)),
            snapshot_id=(str(spec["snapshot_id"]) if spec.get("snapshot_id") is not None else None),
            snapshot_captured_at=spec.get("snapshot_captured_at"))

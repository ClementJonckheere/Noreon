"""Construction du catalogue C4 et du contexte C6 depuis une source canonique.

Les rôles analytiques ne sont jamais dérivés de la seule nature numérique d'une
colonne. Les relations visibles sont conservées avec leur preuve, mais seules
les contraintes système et validations humaines sont exécutables.
"""
from __future__ import annotations

import re

from app.analysis.capability.canonical_catalog import CanonicalRelationCatalog
from app.analysis.capability.model import (
    ADD_FULL,
    Dimension,
    Entity,
    Measure,
    ResolutionContext,
    ResolutionPolicy,
)
from app.analysis.interpreter import PlannerCatalog

_TEMPORAL = ("date", "time", "timestamp")
_ROLES = frozenset({"entity_key", "measure", "dimension", "temporal", "attribute"})
_USABLE_MAPPING_STATUS = frozenset({"validated", "corrected"})


def _tok(*parts: str) -> str:
    raw = "_".join(p for p in parts if p)
    return re.sub(r"[^a-z0-9_]", "_", raw.lower()).strip("_") or "x"


def _semantic_rows(session, connection_id: int):
    try:
        from sqlalchemy import select

        from app.models.semantic import BusinessConcept, ConceptMapping

        query = (
            select(ConceptMapping, BusinessConcept)
            .join(BusinessConcept, ConceptMapping.concept_id == BusinessConcept.id)
            .where(
                ConceptMapping.connection_id == connection_id,
                ConceptMapping.status.in_(["validated", "corrected"]),
            )
        )
        rows = list(session.execute(query).all())
    except Exception:  # noqa: BLE001 - catalogue incomplet, jamais inventé
        return []
    return [
        (mapping, concept) for mapping, concept in rows
        if getattr(mapping, "status", None) in _USABLE_MAPPING_STATUS
    ]


def _candidate_rows(session, connection_id: int, tenant_id: int | None):
    try:
        from sqlalchemy import select

        from app.models.relation_candidate import RelationCandidate

        query = select(RelationCandidate).where(RelationCandidate.connection_id == connection_id)
        if tenant_id is not None:
            query = query.where(RelationCandidate.tenant_id == tenant_id)
        return list(session.execute(query).scalars().all())
    except Exception:  # noqa: BLE001 - table absente / erreur : aucun candidat
        return []


def _load_relations(session, connection_id: int, tenant_id: int | None, tok,
                    snapshot_relations=()):
    canonical = CanonicalRelationCatalog.build(
        db_relations=snapshot_relations,
        candidates=_candidate_rows(session, connection_id, tenant_id),
        tok=tok,
    )
    return list(canonical.relations), canonical.planner_entries()


def _semantic_index(rows) -> dict[tuple[str, str], list[tuple[object, object]]]:
    index: dict[tuple[str, str], list[tuple[object, object]]] = {}
    for mapping, concept in rows:
        key = (str(mapping.table_name).lower(), str(mapping.column_name).lower())
        index.setdefault(key, []).append((mapping, concept))
    for values in index.values():
        values.sort(key=lambda pair: (str(pair[1].name).casefold(), str(pair[0].status)))
    return index


def _mapping_roles(pairs) -> set[str]:
    roles: set[str] = set()
    for mapping, _concept in pairs:
        roles.update(
            role for role in (getattr(mapping, "analytical_roles", None) or [])
            if role in _ROLES
        )
    return roles


def _labels(raw_label: str, pairs) -> tuple[str, list[str]]:
    names: list[str] = []
    for _mapping, concept in pairs:
        names.append(str(concept.name))
        names.extend(str(value) for value in (getattr(concept, "synonyms", None) or []))
    names.append(raw_label)
    unique = list(dict.fromkeys(value for value in names if value))
    return (unique[0] if unique else raw_label), unique


def build_catalog_and_context(session, connection_id: int, *, tenant_id: int | None = None,
                              hidden_tables=None, hidden_columns=None):
    """Renvoie un ``PlannerCatalog`` et un ``ResolutionContext`` cohérents."""
    from app.services.schema_context import current_snapshot

    snap = current_snapshot(session, connection_id)
    if snap is None or not snap.tables:
        return None, None

    hidden_tables = {table.lower() for table in (hidden_tables or set())}
    hidden_columns = {
        (table.lower(), column.lower()) for table, column in (hidden_columns or set())
    }
    semantic = _semantic_index(_semantic_rows(session, connection_id))
    relations, relations_cat = _load_relations(
        session, connection_id, tenant_id, _tok, getattr(snap, "relations", ()) or (),
    )
    relation_keys = {
        key for relation in relations if relation.is_executable
        for key in (relation.from_key, relation.to_key) if key
    }

    concepts_cat: list[dict] = []
    metrics_cat: list[dict] = []
    dims_cat: list[dict] = []
    entities: dict[str, Entity] = {}
    measures: dict[str, Measure] = {}
    dimensions: dict[str, Dimension] = {}
    column_roles: dict[str, tuple[str, ...]] = {}
    hidden_refs: set[str] = set()

    for table in snap.tables:
        table_name = table.table_name
        entity_ref = f"concept:{_tok(table_name)}"
        columns = list(getattr(table, "columns", []) or [])
        primary_keys = tuple(column.name for column in columns
                             if getattr(column, "is_primary_key", False))
        key_types = {
            column.name: (column.data_type or "unknown") for column in columns
            if getattr(column, "is_primary_key", False)
        }
        key_pairs = [
            pair for column in columns
            if getattr(column, "is_primary_key", False)
            for pair in semantic.get((table_name.lower(), column.name.lower()), [])
        ]
        entity_label, entity_aliases = _labels(table_name, key_pairs)
        entities[entity_ref] = Entity(
            ref=entity_ref,
            grain_keys=primary_keys,
            physical=table_name,
            grain_key_types=key_types,
            aliases=tuple(entity_aliases),
        )
        concepts_cat.append({
            "entity_ref": entity_ref,
            "entity_label": entity_label,
            "aliases": entity_aliases,
            "analytical_role": "entity",
        })

        table_hidden = table_name.lower() in hidden_tables
        if table_hidden:
            hidden_refs.add(entity_ref)

        for column in columns:
            data_type = (column.data_type or "").lower()
            physical = f"{table_name}.{column.name}"
            ref_token = _tok(table_name, column.name)
            pairs = semantic.get((table_name.lower(), column.name.lower()), [])
            explicit_roles = _mapping_roles(pairs)
            structural_key = bool(getattr(column, "is_primary_key", False) or physical in relation_keys)
            if explicit_roles:
                roles = set(explicit_roles)
                if structural_key:
                    roles.add("entity_key")
            elif structural_key:
                roles = {"entity_key"}
            elif any(token in data_type for token in _TEMPORAL):
                roles = {"temporal"}
            else:
                roles = {"attribute"}
            column_roles[physical] = tuple(sorted(roles))

            label, aliases = _labels(column.name, pairs)
            column_hidden = table_hidden or (
                table_name.lower(), column.name.lower()
            ) in hidden_columns

            if "measure" in roles:
                ref = f"metric:{ref_token}"
                measures[ref] = Measure(
                    ref=ref,
                    home_entity=entity_ref,
                    additivity=ADD_FULL,
                    physical=physical,
                    data_type=column.data_type,
                    aliases=tuple(aliases),
                )
                metrics_cat.append({
                    "metric_ref": ref,
                    "metric_label": label,
                    "aliases": aliases,
                    "analytical_role": "measure",
                    "data_type": column.data_type,
                })
                if column_hidden:
                    hidden_refs.add(ref)

            if "dimension" in roles or "temporal" in roles:
                ref = f"dimension:{ref_token}"
                is_temporal = "temporal" in roles
                dimensions[ref] = Dimension(
                    ref=ref,
                    home_entity=entity_ref,
                    physical=physical,
                    data_type=column.data_type,
                    is_temporal=is_temporal,
                    aliases=tuple(aliases),
                )
                dims_cat.append({
                    "dimension_ref": ref,
                    "dimension_label": label,
                    "aliases": aliases,
                    "analytical_role": "temporal" if is_temporal else "dimension",
                    "data_type": column.data_type,
                })
                if column_hidden:
                    hidden_refs.add(ref)

    catalog = PlannerCatalog(
        concepts=concepts_cat,
        metrics=metrics_cat,
        dimensions=dims_cat,
        relations=relations_cat,
        stats={},
        domain=getattr(snap, "domain", "") or "",
    )
    context = ResolutionContext(
        entities=entities,
        measures=measures,
        dimensions=dimensions,
        column_roles=column_roles,
        relations=tuple(relations),
        quality={},
        freshness={},
        access={"hidden": hidden_refs, "source_reachable": True},
        policy=ResolutionPolicy(),
        snapshot_id=(str(getattr(snap, "id", "")) or None),
        snapshot_captured_at=(
            getattr(snap, "created_at", None).isoformat()
            if getattr(snap, "created_at", None) else None
        ),
    )
    return catalog, context

"""Construction déterministe des artefacts physiques du resolved_plan v2.

Ce module ne prend aucune décision métier : il fige le contexte C6 en snapshot,
sélectionne un arbre de jointure system-validated et produit des alias stables.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from app.analysis.capability.joinpath import PathStep, find_path
from app.analysis.capability.model import Relation, ResolutionContext
from app.analysis.contracts import CATALOG_SNAPSHOT_SCHEMA_VERSION


def qualify_key(table: str | None, key: str) -> str | None:
    if not table or not key:
        return None
    return key if "." in key else f"{table}.{key}"


def physical_parts(physical: str | None) -> tuple[str | None, str | None]:
    if not physical or "." not in physical:
        return None, None
    table, column = physical.rsplit(".", 1)
    return (table or None), (column or None)


def entity_grain_keys(context: ResolutionContext, entity_ref: str | None) -> list[dict]:
    entity = context.entities.get(entity_ref or "")
    if entity is None:
        return []
    return [
        {
            "physical": qualify_key(entity.physical, key),
            "data_type": entity.grain_key_types.get(key, "unknown"),
        }
        for key in entity.grain_keys
    ]


def catalog_snapshot(context: ResolutionContext) -> dict:
    entities = [
        {
            "ref": entity.ref,
            "physical_table": entity.physical,
            "grain_keys": entity_grain_keys(context, entity.ref),
        }
        for entity in sorted(context.entities.values(), key=lambda value: value.ref)
    ]
    measures = [
        {
            "ref": measure.ref,
            "home_entity_ref": measure.home_entity,
            "physical": measure.physical,
            "data_type": measure.data_type or "unknown",
            "additivity": measure.additivity,
            "non_additive_dimensions": sorted(measure.non_additive_dims),
        }
        for measure in sorted(context.measures.values(), key=lambda value: value.ref)
    ]
    dimensions = [
        {
            "ref": dimension.ref,
            "home_entity_ref": dimension.home_entity,
            "physical": dimension.physical,
            "data_type": dimension.data_type or "unknown",
            "is_temporal": dimension.is_temporal,
        }
        for dimension in sorted(context.dimensions.values(), key=lambda value: value.ref)
    ]
    relations = [
        {
            "id": relation.id,
            "from_entity_ref": relation.from_entity,
            "to_entity_ref": relation.to_entity,
            "from_key": relation.from_key,
            "to_key": relation.to_key,
            "cardinality": relation.cardinality,
            "status": relation.status,
            "origin": relation.origin,
        }
        for relation in sorted(context.relations, key=lambda value: value.id)
        if relation.is_system_validated
    ]
    body = {
        "schema_version": CATALOG_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": context.snapshot_id,
        "captured_at": context.snapshot_captured_at,
        "entities": entities,
        "measures": measures,
        "dimensions": dimensions,
        "relations": relations,
    }
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**body, "fingerprint": hashlib.sha256(canonical.encode()).hexdigest()}


@dataclass
class JoinTreeResult:
    status: str = "resolved"                 # resolved|none|ambiguous
    root_entity_ref: str | None = None
    relation_ids: list[int] = field(default_factory=list)
    missing_target: str | None = None
    ambiguous_target: str | None = None
    alternatives: list = field(default_factory=list)


class _UnionFind:
    def __init__(self, nodes: set[str]):
        self.parent = {node: node for node in nodes}

    def add(self, node: str) -> None:
        self.parent.setdefault(node, node)

    def find(self, node: str) -> str:
        self.add(node)
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def union(self, left: str, right: str) -> bool:
        a, b = self.find(left), self.find(right)
        if a == b:
            return False
        self.parent[b] = a
        return True


def select_join_tree(context: ResolutionContext, root: str | None,
                     targets: set[str]) -> JoinTreeResult:
    if root is None:
        return JoinTreeResult(status="none", missing_target="root_entity")
    selected: list[int] = []
    uf = _UnionFind({root, *targets})
    for target in sorted(targets - {root}):
        path = find_path(context, root, target)
        if path.status == "none":
            return JoinTreeResult(status="none", root_entity_ref=root, missing_target=target)
        if path.status == "ambiguous":
            return JoinTreeResult(
                status="ambiguous", root_entity_ref=root, ambiguous_target=target,
                alternatives=path.alternatives)
        for step in path.steps:
            if step.relation_id in selected:
                uf.union(step.from_entity, step.to_entity)
                continue
            if uf.union(step.from_entity, step.to_entity):
                selected.append(step.relation_id)
    return JoinTreeResult(status="resolved", root_entity_ref=root,
                          relation_ids=sorted(selected))


def _relations(context: ResolutionContext, ids: list[int]) -> dict[int, Relation]:
    wanted = set(ids)
    return {relation.id: relation for relation in context.relations
            if relation.id in wanted and relation.is_system_validated}


def tree_path(context: ResolutionContext, tree: JoinTreeResult,
              source: str, target: str) -> list[PathStep]:
    if source == target:
        return []
    relations = _relations(context, tree.relation_ids)
    adjacent: dict[str, list[PathStep]] = {}
    for relation in relations.values():
        adjacent.setdefault(relation.from_entity, []).append(PathStep(
            relation.id, relation.from_entity, relation.to_entity, relation.cardinality,
            relation.from_key, relation.to_key, relation.coverage, relation.target_uniqueness))
        adjacent.setdefault(relation.to_entity, []).append(PathStep(
            relation.id, relation.to_entity, relation.from_entity, relation.inverse_cardinality,
            relation.to_key, relation.from_key, relation.coverage, relation.target_uniqueness))
    queue: list[tuple[str, list[PathStep]]] = [(source, [])]
    visited = {source}
    while queue:
        node, path = queue.pop(0)
        for step in sorted(adjacent.get(node, []), key=lambda item: item.relation_id):
            if step.to_entity in visited:
                continue
            next_path = [*path, step]
            if step.to_entity == target:
                return next_path
            visited.add(step.to_entity)
            queue.append((step.to_entity, next_path))
    return []


def join_graph(context: ResolutionContext, tree: JoinTreeResult) -> dict:
    root = tree.root_entity_ref
    relations = _relations(context, tree.relation_ids)
    aliases: dict[str, str] = {}
    if root:
        aliases[root] = "t0"
    execution_edges: list[dict] = []
    joined = {root} if root else set()
    pending = set(relations)
    while pending:
        candidates = []
        for relation_id in pending:
            relation = relations[relation_id]
            if relation.from_entity in joined and relation.to_entity not in joined:
                candidates.append((relation_id, relation, False))
            elif relation.to_entity in joined and relation.from_entity not in joined:
                candidates.append((relation_id, relation, True))
        if not candidates:
            break
        relation_id, relation, inverse = sorted(candidates, key=lambda item: item[0])[0]
        if inverse:
            left_ref, right_ref = relation.to_entity, relation.from_entity
            left_key, right_key = relation.to_key, relation.from_key
            cardinality = relation.inverse_cardinality
        else:
            left_ref, right_ref = relation.from_entity, relation.to_entity
            left_key, right_key = relation.from_key, relation.to_key
            cardinality = relation.cardinality
        aliases.setdefault(left_ref, f"t{len(aliases)}")
        aliases.setdefault(right_ref, f"t{len(aliases)}")
        execution_edges.append({
            "validated_relation_id": relation.id,
            "left_entity_ref": left_ref,
            "left_alias": aliases[left_ref],
            "left_key": left_key,
            "right_entity_ref": right_ref,
            "right_alias": aliases[right_ref],
            "right_key": right_key,
            "cardinality": cardinality,
            "fanout_risk": cardinality in ("one_to_many", "many_to_many"),
        })
        joined.add(right_ref)
        pending.remove(relation_id)
    for entity_ref in sorted(joined):
        aliases.setdefault(entity_ref, f"t{len(aliases)}")
    nodes = [
        {
            "entity_ref": entity_ref,
            "physical_table": context.entities.get(entity_ref).physical
            if context.entities.get(entity_ref) else None,
            "alias": alias,
        }
        for entity_ref, alias in sorted(aliases.items(), key=lambda item: int(item[1][1:]))
    ]
    return {
        "root_entity_ref": root,
        "root_alias": aliases.get(root or ""),
        "nodes": nodes,
        "edges": execution_edges,
        "execution_order": [edge["validated_relation_id"] for edge in execution_edges],
    }

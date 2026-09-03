"""Catalogue canonique et auditable des relations analytiques.

La présence d'une relation et son droit d'exécution sont deux faits distincts.
Les contraintes du snapshot et les candidats sont fusionnés, dédupliqués et
conservent leur provenance sans règle liée à un domaine métier.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.analysis.capability.adapter import normalize_cardinality
from app.analysis.capability.model import Relation


def _value(obj, name: str, default=None):
    return getattr(obj, name, default)


def _endpoint(table: str, column: str) -> str:
    return f"{table}.{column}"


def _signature(record: dict) -> tuple[str, str]:
    return tuple(sorted((record["from_key"], record["to_key"])))  # type: ignore[return-value]


def _db_record(row, tok) -> dict:
    declared_constraint = _value(row, "kind", "") == "declared"
    human_validated = _value(row, "status", "") == "validated" and not declared_constraint
    executable = declared_constraint or human_validated
    origin = "constraint" if declared_constraint else _value(row, "kind", "inferred")
    validation_status = (
        "system_validated" if declared_constraint
        else "human_validated" if human_validated
        else "unvalidated"
    )
    status = "validated" if executable else _value(row, "status", "proposed")
    details = dict(_value(row, "details", None) or {})
    evidence = {
        "source": "db_relation",
        "confidence": _value(row, "confidence", None),
        **details,
    }
    coverage = _value(row, "integrity_ratio", None)
    cardinality = _value(row, "cardinality", None)
    if declared_constraint and not cardinality:
        # Une FK cible une clé unique : dans le sens enfant → parent, n→1.
        cardinality = "n-1"
    source_id = int(_value(row, "id"))
    provenance = {
        "source_type": "db_relation",
        "source_id": source_id,
        "origin": origin,
        "status": status,
        "validation_status": validation_status,
    }
    return {
        "id": source_id,
        "source_type": "db_relation",
        "from_entity": f"concept:{tok(_value(row, 'from_table', ''))}",
        "to_entity": f"concept:{tok(_value(row, 'to_table', ''))}",
        "from_key": _endpoint(_value(row, "from_table", ""), _value(row, "from_column", "")),
        "to_key": _endpoint(_value(row, "to_table", ""), _value(row, "to_column", "")),
        "cardinality": normalize_cardinality(cardinality),
        "status": status,
        "origin": origin,
        "direction": "from_to",
        "validation_status": validation_status,
        "coverage": coverage,
        "target_uniqueness": 1.0 if declared_constraint else details.get("target_uniqueness"),
        "evidence": evidence,
        "executable": executable,
        "provenance": [provenance],
    }


def _candidate_record(row, tok) -> dict:
    validated = _value(row, "status", "") == "validated"
    source_id = int(_value(row, "id"))
    origin = _value(row, "origin", "inferred")
    status = _value(row, "status", "candidate")
    validation_status = "human_validated" if validated else "unvalidated"
    evidence = _value(row, "evidence", None)
    if evidence is None:
        evidence = {
            "type_compatibility": _value(row, "type_compatibility", None),
            "exceptions_count": _value(row, "exceptions_count", None),
            "alternatives": _value(row, "alternatives", None),
        }
    provenance = {
        "source_type": "relation_candidate",
        "source_id": source_id,
        "origin": origin,
        "status": status,
        "validation_status": validation_status,
    }
    return {
        "id": source_id,
        "source_type": "relation_candidate",
        "from_entity": f"concept:{tok(_value(row, 'left_table', ''))}",
        "to_entity": f"concept:{tok(_value(row, 'right_table', ''))}",
        "from_key": _endpoint(_value(row, "left_table", ""), _value(row, "left_column", "")),
        "to_key": _endpoint(_value(row, "right_table", ""), _value(row, "right_column", "")),
        "cardinality": normalize_cardinality(_value(row, "cardinality", None)),
        "status": status,
        "origin": origin,
        "direction": _value(row, "direction", "left_to_right"),
        "validation_status": validation_status,
        "coverage": _value(row, "coverage", None),
        "target_uniqueness": _value(row, "target_uniqueness", None),
        "evidence": evidence,
        "executable": validated,
        "provenance": [provenance],
    }


def _authority(record: dict) -> tuple[int, str, int]:
    if record["origin"] == "constraint" and record["executable"]:
        rank = 0
    elif record["executable"]:
        rank = 1
    else:
        rank = 2
    return rank, record["source_type"], record["id"]


@dataclass(frozen=True)
class CanonicalRelationCatalog:
    relations: tuple[Relation, ...]

    @classmethod
    def build(cls, *, db_relations, candidates, tok) -> "CanonicalRelationCatalog":
        records = [_db_record(row, tok) for row in (db_relations or [])]
        records += [_candidate_record(row, tok) for row in (candidates or [])]
        records.sort(key=lambda record: (_authority(record), _signature(record)))

        deduped: dict[tuple[str, str], dict] = {}
        for record in records:
            signature = _signature(record)
            current = deduped.get(signature)
            if current is None:
                deduped[signature] = record
                continue
            current["provenance"].extend(record["provenance"])

        used_ids: dict[int, tuple[str, str]] = {}
        relations: list[Relation] = []
        for signature, record in sorted(deduped.items(), key=lambda item: (_authority(item[1]), item[0])):
            relation_id = record["id"]
            if relation_id in used_ids and used_ids[relation_id] != signature:
                relation_id = -abs(relation_id)
                while relation_id in used_ids:
                    relation_id -= 1
            used_ids[relation_id] = signature
            provenance = tuple(sorted(
                record["provenance"],
                key=lambda item: (item["source_type"], item["source_id"]),
            ))
            relations.append(Relation(
                id=relation_id,
                from_entity=record["from_entity"],
                to_entity=record["to_entity"],
                cardinality=record["cardinality"],
                from_key=record["from_key"],
                to_key=record["to_key"],
                status=record["status"],
                origin=record["origin"],
                coverage=record["coverage"],
                target_uniqueness=record["target_uniqueness"],
                direction=record["direction"],
                validation_status=record["validation_status"],
                evidence=record["evidence"],
                provenance=provenance,
                executable=record["executable"],
            ))
        return cls(tuple(sorted(relations, key=lambda relation: relation.id)))

    def planner_entries(self) -> list[dict]:
        return [
            {
                "relation_ref": f"relation:{relation.id}",
                "from_entity_ref": relation.from_entity,
                "to_entity_ref": relation.to_entity,
                "from_key": relation.from_key,
                "to_key": relation.to_key,
                "direction": relation.direction,
                "cardinality": relation.cardinality,
                "origin": relation.origin,
                "status": relation.status,
                "validation_status": relation.validation_status,
                "executable": relation.is_executable,
                "coverage": relation.coverage,
                "target_uniqueness": relation.target_uniqueness,
                "evidence": relation.evidence,
                "provenance": list(relation.provenance),
            }
            for relation in self.relations
        ]

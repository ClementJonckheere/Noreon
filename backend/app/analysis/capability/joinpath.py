"""Phase 2 — C6 : résolution des chemins de jointure, SAFETY-FIRST (#4).

Uniquement des relations SYSTEM-VALIDATED (`status=validated` OU `origin=constraint`,
#6). Le tri privilégie la SÛRETÉ (moins de fanout, éviter n↔n) AVANT la brièveté.
Aucun chemin inventé : pas de relation validée ⇒ `none` (→ unresolved en amont).
Chemins également sûrs et courts ⇒ `ambiguous` (→ clarification).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.analysis.capability.grain import step_multiplies
from app.analysis.capability.model import MANY_TO_MANY, ResolutionContext


@dataclass(frozen=True)
class PathStep:
    relation_id: int
    from_entity: str
    to_entity: str
    cardinality: str                 # dans le sens de PARCOURS
    from_key: str | None
    to_key: str | None
    coverage: float | None = None
    target_uniqueness: float | None = None


@dataclass
class PathResult:
    status: str                      # resolved | ambiguous | none
    steps: list[PathStep] = field(default_factory=list)
    alternatives: list = field(default_factory=list)


def _edges(context: ResolutionContext):
    """Arêtes dirigées à partir des relations system-validated (aller + retour)."""
    adj: dict[str, list] = {}
    for r in context.relations:
        if not r.is_system_validated:
            continue
        adj.setdefault(r.from_entity, []).append(PathStep(
            r.id, r.from_entity, r.to_entity, r.cardinality, r.from_key, r.to_key,
            r.coverage, r.target_uniqueness))
        adj.setdefault(r.to_entity, []).append(PathStep(
            r.id, r.to_entity, r.from_entity, r.inverse_cardinality, r.to_key, r.from_key,
            r.coverage, r.target_uniqueness))
    return adj


def _enumerate(adj, source: str, target: str, max_depth: int):
    paths: list[list[PathStep]] = []
    def dfs(node, visited, acc):
        if len(acc) > max_depth:
            return
        if node == target and acc:
            paths.append(list(acc)); return
        for step in adj.get(node, []):
            if step.to_entity in visited:
                continue
            dfs(step.to_entity, visited | {step.to_entity}, acc + [step])
    if source == target:
        return [[]]
    dfs(source, {source}, [])
    return paths


def _score(path: list[PathStep]):
    """Clé de tri SAFETY-FIRST : d'abord la sûreté, ensuite la brièveté."""
    n_nn = sum(1 for s in path if s.cardinality == MANY_TO_MANY)
    n_fanout = sum(1 for s in path if step_multiplies(s.cardinality))
    min_cov = min([s.coverage for s in path if s.coverage is not None], default=1.0)
    min_uni = min([s.target_uniqueness for s in path if s.target_uniqueness is not None], default=1.0)
    return (n_nn, n_fanout, len(path), -min_cov, -min_uni)


def find_path(context: ResolutionContext, source: str, target: str) -> PathResult:
    if source == target:
        return PathResult("resolved", [])
    adj = _edges(context)
    paths = _enumerate(adj, source, target, context.policy.max_path_depth)
    if not paths:
        return PathResult("none")
    paths.sort(key=_score)
    best = paths[0]
    # Ambiguïté : un autre chemin est aussi sûr ET aussi court (mêmes 3 premiers critères).
    if len(paths) > 1 and _score(paths[1])[:3] == _score(best)[:3] \
            and {s.relation_id for s in paths[1]} != {s.relation_id for s in best}:
        return PathResult("ambiguous", best,
                          alternatives=[[s.relation_id for s in p] for p in paths[:3]])
    return PathResult("resolved", best)

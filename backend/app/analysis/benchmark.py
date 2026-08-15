"""Phase 2 — C3 : harnais de benchmark des modèles de planification.

Compare des modèles sur le jeu d'éval avec des SEUILS ÉLIMINATOIRES : le score
n'est pas une moyenne qui laisserait une bonne latence compenser une faute grave.
Un modèle est ÉLIMINÉ (score 0) si, sur un seul cas :
  - il utilise une référence hors catalogue (inventée) ;
  - il oublie l'objectif principal ;
  - il substitue silencieusement une autre analyse (tendance/attribution non
    demandée en objectif principal) ;
et globalement s'il descend sous :
  - 99 % de sorties JSON conformes (après le nombre de tentatives autorisé) ;
  - 95 % de rappel des objectifs.
Le coût et la latence ne DÉPARTAGENT que les modèles ayant passé ces seuils.

Le benchmark s'exécute côté opérateur (clé requise). Ici : la logique de scoring,
testable de façon déterministe. Aucun modèle n'est retenu avant ce benchmark.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.analysis.contracts import ContractError, Interpretation
from app.analysis.eval_cases import EvalCase

_SUBSTITUTION_TYPES = frozenset({"trend", "attribution"})   # « défauts » fabriqués
JSON_CONFORMITY_MIN = 0.99
RECALL_MIN = 0.95


def catalog_refs(catalog) -> set[str]:
    """Ensemble des références sémantiques présentes dans le catalogue."""
    refs: set[str] = set()
    for grp in (catalog.concepts, catalog.metrics, catalog.dimensions, catalog.relations):
        for e in grp or []:
            for v in e.values():
                if isinstance(v, str) and ":" in v and v.split(":", 1)[0] in {"concept", "metric", "dimension"}:
                    refs.add(v)
    return refs


def _refs_used(interp: Interpretation) -> set[str]:
    used: set[str] = set()
    for g in interp.goals:
        if g.entity_ref:
            used.add(g.entity_ref)
        for m in g.raw.get("metrics") or []:
            for k in ("ref", "of_ref"):
                if isinstance(m.get(k), str):
                    used.add(m[k])
        for d in g.raw.get("dimensions") or []:
            if isinstance(d.get("ref"), str):
                used.add(d["ref"])
    return used


@dataclass
class CaseResult:
    case_id: str
    json_ok: bool
    recall: float = 0.0
    out_of_catalog: bool = False
    primary_forgotten: bool = False
    silent_substitution: bool = False
    error: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def score_case(case: EvalCase, interp: Interpretation | None, refs: set[str]) -> CaseResult:
    if interp is None:
        return CaseResult(case.case_id if hasattr(case, "case_id") else case.id,
                          json_ok=False, error="sortie non conforme")
    produced = {g.type for g in interp.goals}
    expected = set(case.expect_types)
    recall = len(expected & produced) / len(expected) if expected else 1.0
    primary = min(interp.goals, key=lambda g: g.priority)
    out_of_catalog = bool(_refs_used(interp) - refs)
    primary_forgotten = primary.type not in expected
    # Substitution : l'objectif principal est un « défaut » (tendance/attribution)
    # alors qu'il n'était pas demandé.
    silent_substitution = primary.type in _SUBSTITUTION_TYPES and primary.type not in expected
    return CaseResult(case.id, json_ok=True, recall=recall, out_of_catalog=out_of_catalog,
                      primary_forgotten=primary_forgotten, silent_substitution=silent_substitution)


@dataclass
class ModelReport:
    model: str
    results: list[CaseResult] = field(default_factory=list)
    latency_ms_mean: float | None = None
    cost: float | None = None

    @property
    def json_conformity(self) -> float:
        return sum(r.json_ok for r in self.results) / len(self.results) if self.results else 0.0

    @property
    def recall_mean(self) -> float:
        ok = [r.recall for r in self.results if r.json_ok]
        return sum(ok) / len(ok) if ok else 0.0

    def elimination_reasons(self) -> list[str]:
        reasons: list[str] = []
        if any(r.out_of_catalog for r in self.results):
            reasons.append("référence hors catalogue")
        if any(r.primary_forgotten for r in self.results):
            reasons.append("objectif principal oublié")
        if any(r.silent_substitution for r in self.results):
            reasons.append("substitution silencieuse")
        if self.json_conformity < JSON_CONFORMITY_MIN:
            reasons.append(f"JSON conforme {self.json_conformity:.0%} < {JSON_CONFORMITY_MIN:.0%}")
        if self.recall_mean < RECALL_MIN:
            reasons.append(f"rappel {self.recall_mean:.0%} < {RECALL_MIN:.0%}")
        return reasons

    @property
    def eliminated(self) -> bool:
        return bool(self.elimination_reasons())

    def as_dict(self) -> dict:
        return {
            "model": self.model, "eliminated": self.eliminated,
            "elimination_reasons": self.elimination_reasons(),
            "json_conformity": round(self.json_conformity, 4),
            "recall_mean": round(self.recall_mean, 4),
            "latency_ms_mean": self.latency_ms_mean, "cost": self.cost,
            "cases": [r.as_dict() for r in self.results],
        }


def run_benchmark(model: str, cases: list[EvalCase], catalog, *, plan_fn, attempts: int = 2) -> ModelReport:
    """`plan_fn(model, question, catalog) -> Interpretation` (lève ContractError si
    non conforme). Réessaie jusqu'à `attempts` fois avant de compter un échec JSON."""
    refs = catalog_refs(catalog)
    report = ModelReport(model=model)
    latencies: list[float] = []
    for case in cases:
        interp = None
        for _ in range(max(1, attempts)):
            t0 = time.perf_counter()
            try:
                interp = plan_fn(model, case.question, catalog)
                latencies.append((time.perf_counter() - t0) * 1000)
                break
            except ContractError:
                interp = None
        report.results.append(score_case(case, interp, refs))
    report.latency_ms_mean = round(sum(latencies) / len(latencies), 1) if latencies else None
    return report


def rank(reports: list[ModelReport]) -> list[ModelReport]:
    """Modèles éliminés en dernier ; les qualifiés départagés par latence (à
    défaut de coût). Aucun modèle retenu s'ils sont tous éliminés."""
    def key(r: ModelReport):
        return (r.eliminated, r.latency_ms_mean if r.latency_ms_mean is not None else float("inf"))
    return sorted(reports, key=key)

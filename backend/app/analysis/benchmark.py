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
    false_goals: int = 0            # objectifs de type NON attendu
    n_goals: int = 0
    has_dependencies: bool = False
    has_ambiguities: bool = False
    network_incident: bool = False  # panne réseau/timeout — distinct du JSON non conforme
    retries: int = 1
    latency_ms: float | None = None
    tokens: int | None = None
    cost: float | None = None
    routing_excluded: bool | None = None   # (tier simple, cas complexe) le pré-routeur l'aurait exclu
    semantic: bool = True           # évalué sémantiquement (sinon : conformité seule)
    error: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def score_case(case: EvalCase, interp: Interpretation | None, refs: set[str]) -> CaseResult:
    if interp is None:
        return CaseResult(case.id, json_ok=False, error="sortie non conforme")
    produced = {g.type for g in interp.goals}
    expected = set(case.expect_types)
    recall = len(expected & produced) / len(expected) if expected else 1.0
    primary = min(interp.goals, key=lambda g: g.priority)
    out_of_catalog = bool(_refs_used(interp) - refs)
    primary_forgotten = primary.type not in expected
    silent_substitution = primary.type in _SUBSTITUTION_TYPES and primary.type not in expected
    return CaseResult(
        case.id, json_ok=True, recall=recall, out_of_catalog=out_of_catalog,
        primary_forgotten=primary_forgotten, silent_substitution=silent_substitution,
        false_goals=len(produced - expected), n_goals=len(interp.goals),
        has_dependencies=any(g.depends_on for g in interp.goals),
        has_ambiguities=any(g.raw.get("ambiguities") for g in interp.goals))


@dataclass
class ModelReport:
    model: str
    tier: str = "main"                       # main (corpus complet) | simple (sous-ensemble)
    results: list[CaseResult] = field(default_factory=list)
    cost: float | None = None

    def _non_network(self) -> list[CaseResult]:
        return [r for r in self.results if not r.network_incident]

    def _semantic(self) -> list[CaseResult]:
        return [r for r in self.results if r.semantic and r.json_ok]

    @property
    def json_conformity(self) -> float:
        # Conformité STRUCTURELLE, incidents réseau EXCLUS (comptés à part).
        base = self._non_network()
        return sum(r.json_ok for r in base) / len(base) if base else 0.0

    @property
    def recall_mean(self) -> float:
        sem = self._semantic()
        return sum(r.recall for r in sem) / len(sem) if sem else 0.0

    @property
    def network_incidents(self) -> int:
        return sum(r.network_incident for r in self.results)

    @property
    def latency_ms_mean(self) -> float | None:
        lat = [r.latency_ms for r in self.results if r.latency_ms is not None]
        return round(sum(lat) / len(lat), 1) if lat else None

    @property
    def routing_leaks(self) -> int:
        # (tier simple) cas complexes que le pré-routeur AURAIT sélectionnés pour le 20b.
        return sum(1 for r in self.results if r.routing_excluded is False)

    def elimination_reasons(self) -> list[str]:
        sem = self._semantic()
        reasons: list[str] = []
        if any(r.out_of_catalog for r in sem):
            reasons.append("référence hors catalogue")
        if any(r.primary_forgotten for r in sem):
            reasons.append("objectif principal oublié")
        if any(r.silent_substitution for r in sem):
            reasons.append("substitution silencieuse")
        if self.json_conformity < JSON_CONFORMITY_MIN:
            reasons.append(f"JSON conforme {self.json_conformity:.1%} < {JSON_CONFORMITY_MIN:.0%}")
        if sem and self.recall_mean < RECALL_MIN:
            reasons.append(f"rappel {self.recall_mean:.1%} < {RECALL_MIN:.0%}")
        if self.routing_leaks:
            reasons.append(f"{self.routing_leaks} cas complexes non exclus par le pré-routeur")
        return reasons

    @property
    def eliminated(self) -> bool:
        return bool(self.elimination_reasons())

    def as_dict(self) -> dict:
        toks = [r.tokens for r in self.results if r.tokens is not None]
        return {
            "model": self.model, "tier": self.tier, "eliminated": self.eliminated,
            "elimination_reasons": self.elimination_reasons(),
            "json_conformity": round(self.json_conformity, 4),
            "recall_mean": round(self.recall_mean, 4),
            "semantic_cases": len(self._semantic()),
            "false_goals_total": sum(r.false_goals for r in self._semantic()),
            "network_incidents": self.network_incidents,
            "retries_total": sum(r.retries for r in self.results),
            "routing_leaks": self.routing_leaks,
            "latency_ms_mean": self.latency_ms_mean,
            "tokens_total": sum(toks) if toks else None, "cost": self.cost,
            "cases": [r.as_dict() for r in self.results],
        }


@dataclass
class PlanResult:
    """Sortie d'un appel de planification (le CLI capture latence/tokens/tentatives)."""
    interp: Interpretation | None
    error_kind: str = "none"     # none | contract | network
    latency_ms: float | None = None
    tokens: int | None = None
    cost: float | None = None
    attempts: int = 1


def run_model(model: str, cases: list[EvalCase], catalog, *, plan_fn,
              tier: str = "main", main_model: str | None = None,
              simple_model: str | None = None, max_workers: int = 1,
              progress=None) -> ModelReport:
    """`plan_fn(model, question, catalog) -> PlanResult`.

    tier=main : évaluation SÉMANTIQUE sur tout le corpus.
    tier=simple : sémantique UNIQUEMENT sur les cas `simple_eligible` ; sur les
    autres, on mesure la conformité JSON et on vérifie que le pré-routeur les
    aurait EXCLUS du 20b (aucune sélection silencieuse).

    `max_workers>1` parallélise les appels (I/O réseau) SANS changer l'ordre des
    résultats — les appels `plan` ne mutent aucun état partagé. `progress(done,
    total, case, res)` est appelé à chaque cas terminé (feedback en direct)."""
    from app.analysis.routing import preroute

    refs = catalog_refs(catalog)
    report = ModelReport(model=model, tier=tier)

    def _eval_one(case: EvalCase) -> CaseResult:
        pr = plan_fn(model, case.question, catalog)
        semantic = (tier == "main") or case.simple_eligible
        if pr.interp is None:
            res = CaseResult(case.id, json_ok=False, semantic=semantic,
                             network_incident=(pr.error_kind == "network"),
                             error=pr.error_kind, retries=pr.attempts,
                             latency_ms=pr.latency_ms)
        else:
            res = score_case(case, pr.interp, refs)
            res.semantic = semantic
            res.retries = pr.attempts
            res.latency_ms = pr.latency_ms
            res.tokens = pr.tokens
            res.cost = pr.cost
        if tier == "simple" and not case.simple_eligible and simple_model:
            dec = preroute(case.question, main_model=main_model or "main", simple_model=simple_model)
            res.routing_excluded = dec.selected_model != simple_model
        return res

    total = len(cases)
    if max_workers and max_workers > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        ordered: list[CaseResult | None] = [None] * total
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(_eval_one, c): i for i, c in enumerate(cases)}
            done = 0
            for fut in as_completed(futs):
                i = futs[fut]
                ordered[i] = fut.result()
                done += 1
                if progress:
                    progress(done, total, cases[i], ordered[i])
        report.results = [r for r in ordered if r is not None]
    else:
        for idx, case in enumerate(cases, 1):
            res = _eval_one(case)
            report.results.append(res)
            if progress:
                progress(idx, total, case, res)
    return report


def preflight(provider, *, sample_schema: dict | None = None) -> dict:
    """Vérifie que le modèle répond ET supporte `response_format=json_schema`.
    Aucune donnée réelle : un prompt minimal. Renvoie {ok, json_schema, error}."""
    from app.analysis.schema_models import interpretation_json_schema
    schema = sample_schema or interpretation_json_schema()
    try:
        raw = provider.plan(system="ping", user="{}", json_schema=schema)
        return {"ok": True, "json_schema": True, "sample": (raw or "")[:120], "error": None}
    except Exception as exc:  # noqa: BLE001 - préflight best-effort
        return {"ok": False, "json_schema": False, "error": f"{type(exc).__name__}: {exc}"}


def rank(reports: list[ModelReport]) -> list[ModelReport]:
    """Modèles éliminés en dernier ; les qualifiés départagés par latence (à
    défaut de coût). Aucun modèle retenu s'ils sont tous éliminés."""
    def key(r: ModelReport):
        return (r.eliminated, r.latency_ms_mean if r.latency_ms_mean is not None else float("inf"))
    return sorted(reports, key=key)

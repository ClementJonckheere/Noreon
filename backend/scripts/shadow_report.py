#!/usr/bin/env python3
"""Phase 2 — shadow : rapport de campagne (lit planner_shadow_evaluations).

Ne donne PAS un simple « taux d'accord » : décompose LLM contract, comparaison,
résolution capability (C6), sécurité analytique et routage, puis détaille les
divergences matérielles, les écarts de sécurité (llm_safer/fallback_safer), les
réparations et les erreurs.

  python scripts/shadow_report.py [--limit 200] [--tenant 1]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal                                   # noqa: E402
from app.analysis.shadow.diagnostics import summarize_observations     # noqa: E402
from app.analysis.shadow.export import serialize_row                   # noqa: E402
from app.models.planner_shadow import PlannerShadowEvaluation as PSE   # noqa: E402
from sqlalchemy import select                                          # noqa: E402


def _rows(limit: int, tenant: int | None):
    with SessionLocal() as s:
        q = select(PSE).order_by(PSE.created_at.desc())
        if tenant is not None:
            q = q.where(PSE.tenant_id == tenant)
        return list(s.execute(q.limit(limit)).scalars().all())


def _bar(title): print("\n" + title)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--tenant", type=int, default=None)
    args = ap.parse_args()

    rows = _rows(args.limit, args.tenant)
    n = len(rows)
    if not n:
        print("Aucune évaluation shadow trouvée. Lancer une campagne en PLANNER_MODE=shadow.")
        return 0

    print(f"SHADOW RUN — {n} requêtes")

    _bar("LLM CONTRACT")
    ok = sum(r.llm_status == "ok" for r in rows)
    repairs = sum(bool(r.repair_applied) for r in rows)
    prov_err = sum(r.llm_status in ("network_error", "provider_error", "timeout") for r in rows)
    contract_err = sum(r.llm_status == "contract_error" for r in rows)
    print(f"  ok                        {ok}/{n}")
    print(f"  repairs                   {repairs}/{n} ({repairs / n:.1%})")
    print(f"  contract errors           {contract_err}")
    print(f"  provider/network errors   {prov_err}")

    _bar("COMPARISON")
    for k, v in Counter(r.comparison_outcome for r in rows).most_common():
        print(f"  {str(k):<24} {v}")

    _bar("CAPABILITY RESOLUTION (exigences cumulées)")
    caps = Counter()
    for r in rows:
        for state, c in (r.capability_states_json or {}).items():
            caps[state] += c
    for state in ("available", "available_with_reserve", "unresolved", "not_evaluated", "blocked"):
        print(f"  {state:<24} {caps.get(state, 0)}")

    diagnostics = summarize_observations([serialize_row(row) for row in rows])
    semantic = diagnostics["goal_semantic_completeness"]
    _bar("P0-C ACCEPTANCE")
    print(f"  goal semantic completeness {semantic['complete']}/{semantic['total']} "
          f"({semantic['rate']:.1%})")
    for key, label in (
        ("goal_without_operand_and_without_reason", "goal sans opérande/raison"),
        ("diagnostic_cascade_count", "diagnostics cascade"),
        ("known_refs_false_unresolved", "known refs false unresolved"),
        ("resolved_semantic_ready_goals", "goals sémantiquement résolus"),
        ("compile_ready_goals", "goals compile-ready"),
        ("required_unresolved", "unresolved required"),
        ("optional_unresolved", "unresolved optional"),
        ("relations_constraint_present", "relations constraint exécutables"),
        ("relations_inferred_nonvalidated_ignored", "relations inferred ignorées"),
        ("aggregation_contradictions", "contradictions agrégation"),
    ):
        print(f"  {label:<32} {diagnostics[key]}")
    for status in ("SUPPORTED", "PARTIAL", "UNSUPPORTED", "NEEDS_CLARIFICATION"):
        print(f"  goals {status:<26} {diagnostics['goal_statuses'].get(status, 0)}")

    _bar("ANALYTICAL SAFETY")
    for state in ("same_safety", "llm_safer", "fallback_safer", "not_comparable"):
        print(f"  {state:<24} {sum(r.analytical_safety == state for r in rows)}")

    _bar("ROUTING")
    for model, c in Counter(r.candidate_model for r in rows).most_common():
        print(f"  {str(model):<24} {c}")
    print(f"  escalations              {sum(bool(r.escalated) for r in rows)}")

    # --- détails ------------------------------------------------------------
    mats = [r for r in rows if r.comparison_outcome == "material_divergence"]
    if mats:
        _bar(f"DÉTAIL — divergences matérielles ({len(mats)})")
        for r in mats:
            facets = (r.comparison_json or {}).get("facets", {})
            diff = [f for f, d in facets.items() if isinstance(d, dict) and d.get("state") == "disagree"]
            print(f"  · {r.request_id} · candidat {r.candidate_model} · facettes en désaccord : {diff}")

    safeties = [r for r in rows if r.analytical_safety in ("llm_safer", "fallback_safer")]
    if safeties:
        _bar(f"DÉTAIL — écarts de sécurité analytique ({len(safeties)}) — REVUE PRIORITAIRE")
        for r in safeties:
            why = (r.analytical_safety_json or {}).get("why", "")
            print(f"  · {r.request_id} · {r.analytical_safety} · {why}")

    reps = [r for r in rows if r.repair_applied]
    if reps:
        _bar(f"DÉTAIL — réparations ({len(reps)})")
        for r in reps:
            print(f"  · {r.request_id} · {r.repair_type} · {(r.repair_details_json or {}).get('duplicates')}")

    errs = [r for r in rows if r.llm_status not in ("ok",)]
    if errs:
        _bar(f"DÉTAIL — erreurs LLM ({len(errs)})")
        for r in errs:
            print(f"  · {r.request_id} · {r.llm_status} · {r.error_detail or ''}")

    print("\n(Le fallback reste une COMPARAISON, jamais la vérité terrain. "
          "llm_safer/fallback_safer = investigation, pas activation.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

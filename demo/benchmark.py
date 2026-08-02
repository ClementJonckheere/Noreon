#!/usr/bin/env python3
"""Framework de non-régression — Gold Standard → Noreon → écart → score.

Pour chaque scénario, on compare la sortie RÉELLE du moteur à la vérité attendue
(`demo/<scenario>/expected.json`, projection machine-vérifiable du Gold Standard)
et on produit un **bulletin** noté sur 100. Utilisable en CI : sortie non nulle si
un scénario passe sous le seuil.

    cd backend && python ../demo/benchmark.py            # tous les scénarios
    cd backend && python ../demo/benchmark.py retail crm # ciblés
    cd backend && python ../demo/benchmark.py --threshold 90

Chaque scénario dont la base source est injoignable est marqué SKIP (non compté).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _runner import SCENARIO_QUESTIONS, analyze, db_available  # noqa: E402

HERE = Path(__file__).resolve().parent
PASS_THRESHOLD = 80  # score minimal pour valider un scénario

# Barème : (clé, libellé, poids). Total = 100.
RUBRIC = [
    ("intent", "Intention comprise", 10),
    ("trend", "Sens de la variation", 15),
    ("attr_dim", "Bon axe causal", 25),
    ("attr_seg", "Bon segment", 25),
    ("attr_contrib", "Contribution suffisante", 15),
    ("role", "Bon décideur (★≥4)", 10),
]


def _norm(s) -> str:
    return str(s or "").lower()


def _extract(r) -> dict:
    """Projette la réponse Noreon sur les champs vérifiables."""
    inv = r.investigation or {}
    attr = inv.get("attribution") or {}
    return {
        "intent": _norm(r.intent),
        "trend": _norm((r.chronicle or {}).get("direction")),
        "attr_dim": _norm(attr.get("dimension")),
        "attr_seg": _norm(attr.get("segment")),
        "attr_contrib": attr.get("contribution_pct"),
        "decisions": (r.decisions or {}).get("decisions", []),
    }


def _score(got: dict, exp: dict) -> list[tuple]:
    """Renvoie [(clé, libellé, poids, ok, détail)] pour chaque critère du barème."""
    a = exp["attribution"]
    checks = {
        "intent": (got["intent"] == exp["intent"], f"{got['intent'] or '—'}"),
        "trend": (got["trend"] == _norm(exp["trend_direction"]), f"{got['trend'] or '—'}"),
        "attr_dim": (_norm(a["dimension_contains"]) in got["attr_dim"],
                     got["attr_dim"] or "—"),
        "attr_seg": (_norm(a["segment_contains"]) in got["attr_seg"],
                     got["attr_seg"] or "—"),
        "attr_contrib": (isinstance(got["attr_contrib"], (int, float))
                         and got["attr_contrib"] >= a["min_contribution_pct"],
                         f"{got['attr_contrib']}%" if got["attr_contrib"] is not None else "—"),
        "role": _role_ok(got["decisions"], exp["lead_role"]),
    }
    return [(k, lbl, w, checks[k][0], checks[k][1]) for k, lbl, w in RUBRIC]


def _role_ok(decisions: list, expected_role: str) -> tuple[bool, str]:
    for d in decisions:
        if _norm(expected_role) in _norm(d.get("role")) and d.get("stars", 0) >= 4:
            return True, f"{d['role']} ({d.get('stars')}★)"
    top = decisions[0]["role"] if decisions else "—"
    return False, f"attendu « {expected_role} » ; en tête : {top}"


def run(scenarios: list[str], threshold: int) -> int:
    print("\n" + "═" * 78)
    print(" BENCHMARK — Gold Standard ⇄ Noreon")
    print("═" * 78)
    total, counted, failures = 0, 0, 0
    for sc in scenarios:
        exp = json.loads((HERE / sc / "expected.json").read_text(encoding="utf-8"))
        if not db_available(sc):
            print(f"\n▹ {sc:<14} SKIP — base noreon_demo_{sc} injoignable "
                  f"(lancer demo/setup_scenario.sh {sc}).")
            continue
        r, _ = analyze(sc, exp["question"])
        rows = _score(_extract(r), exp)
        got_pts = sum(w for _, _, w, ok, _ in rows if ok)
        counted += 1
        total += got_pts
        status = "✅ PASS" if got_pts >= threshold else "❌ FAIL"
        if got_pts < threshold:
            failures += 1
        print(f"\n▹ {sc:<14} {got_pts:3d}/100  {status}")
        for _, lbl, w, ok, detail in rows:
            mark = "✓" if ok else "✗"
            print(f"    {mark} {lbl:<28} {w:>2} pts   {detail}")

    if counted:
        avg = total / counted
        print("\n" + "─" * 78)
        print(f" MOYENNE : {avg:.0f}/100 sur {counted} scénario(s) · "
              f"{counted - failures} PASS / {failures} FAIL · seuil {threshold}")
        print("─" * 78)
    else:
        print("\nAucune base de démo joignable. Lancez demo/setup_scenario.sh <scenario>.")
        return 0
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    threshold = PASS_THRESHOLD
    args = []
    i = 0
    while i < len(argv):
        if argv[i] == "--threshold":
            threshold = int(argv[i + 1])
            i += 2
        else:
            args.append(argv[i])
            i += 1
    scenarios = args or list(SCENARIO_QUESTIONS)
    unknown = [s for s in scenarios if s not in SCENARIO_QUESTIONS]
    if unknown:
        print(f"Scénario(s) inconnu(s) : {', '.join(unknown)}")
        return 2
    return run(scenarios, threshold)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

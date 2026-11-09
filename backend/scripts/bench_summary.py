#!/usr/bin/env python3
"""Phase 2 — C3b : résumé lisible d'un rapport de benchmark (bench_report.json).

Évite de coller un bloc PowerShell fragile : lit le JSON produit par
`bench_planner.py` et imprime, par catalogue, l'essentiel pour décider des
modèles (éliminé ou non, rappel, conformité JSON, latence, fuites de routage,
accord 20b/120b). N'appelle AUCUN modèle, ne lit aucune donnée réelle.

Usage :
  python scripts/bench_summary.py                 # lit ./bench_report.json
  python scripts/bench_summary.py chemin/vers.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _fmt(x, suffix: str = "") -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.3f}{suffix}"
    return f"{x}{suffix}"


def _model_line(label: str, rep: dict) -> str:
    state = "ÉLIMINÉ" if rep.get("eliminated") else "qualifié"
    reasons = "; ".join(rep.get("elimination_reasons") or []) or "OK"
    return (f"  {label:<7}{rep.get('model')}: {state}"
            f" · rappel={_fmt(rep.get('recall_mean'))}"
            f" · json={_fmt(rep.get('json_conformity'))}"
            f" · latence={_fmt(rep.get('latency_ms_mean'), ' ms')}"
            f" · incidents_réseau={rep.get('network_incidents')}"
            f" · fuites_routage={rep.get('routing_leaks')}"
            f"\n           faux_objectifs={rep.get('false_goals_total')}"
            f" · cas_sémantiques={rep.get('semantic_cases')}"
            f" · tokens={_fmt(rep.get('tokens_total'))}"
            f"\n           → {reasons}")


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("bench_report.json")
    if not path.is_file():
        print(f"ERREUR : rapport introuvable : {path}", file=sys.stderr)
        print("Lance d'abord scripts/bench_planner.py, ou passe le chemin en argument.",
              file=sys.stderr)
        return 2
    report = json.loads(path.read_text(encoding="utf-8"))

    print(f"Rapport : {path}")
    print(f"Modèles : principal={report.get('main_model')} · simple={report.get('simple_model')}")
    print(f"Split : {report.get('split')} · runs : {report.get('runs')}")
    print("=" * 72)

    catalogs = report.get("catalogs") or {}
    if not catalogs:
        print("(aucun catalogue dans le rapport)")
        return 1

    any_main_elim = any_simple_elim = False
    for name, block in catalogs.items():
        main_rep = block.get("main") or {}
        simple_rep = block.get("simple") or {}
        any_main_elim |= bool(main_rep.get("eliminated"))
        any_simple_elim |= bool(simple_rep.get("eliminated"))
        print(f"\n[{name}]")
        print(_model_line("main", main_rep))
        print(_model_line("simple", simple_rep))
        print(f"  accord 20b↔120b (cas simples) : "
              f"{_fmt(block.get('agreement_20b_vs_120b_on_simple'))}")

    print("\n" + "=" * 72)
    print("VERDICT GLOBAL")
    print(f"  Modèle principal ({report.get('main_model')}) : "
          f"{'ÉLIMINÉ sur ≥1 catalogue' if any_main_elim else 'qualifié partout'}")
    print(f"  Modèle simple ({report.get('simple_model')}) : "
          f"{'ÉLIMINÉ sur ≥1 catalogue' if any_simple_elim else 'qualifié partout'}")
    print("  (Routage de production TOUJOURS désactivé — décision manuelle.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

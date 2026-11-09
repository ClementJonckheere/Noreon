#!/usr/bin/env python3
"""Phase 2 — C6 : lance le benchmark déterministe du CapabilityResolver.

Affiche des taux PAR DIMENSION (pas de score opaque) et la liste des VIOLATIONS
de sécurité analytique (éliminatoires). Aucun LLM, aucune DB : pur déterministe.

  python scripts/bench_resolver.py              # rapport
  python scripts/bench_resolver.py --update      # (re)génère les snapshots de référence
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.capability import resolver_eval as E   # noqa: E402


def main() -> int:
    if "--update" in sys.argv[1:]:
        sigs = E.write_snapshots()
        print(f"Snapshots (re)générés : {len(sigs)} cas → {E._SNAPSHOT_PATH.name}")
        return 0

    rep = E.run_eval()
    print(f"CapabilityResolver — {rep['n_cases']} cas · domaines {rep['domains']}")
    print("=" * 64)
    print("Taux par dimension (attendu vs produit) :")
    for dim, rate in rep["dimension_rates"].items():
        print(f"  {dim:<10} : {rate:.0%}")

    print("\nDétail par cas :")
    print(f"  {'cas':<24}{'dom':<8}{'status':<14}{'strat':<16}{'fanout':<7}snapshot")
    for r in rep["results"]:
        p = r.produced
        flag = "" if all(r.matches.values()) else "  ✗ écart attendu"
        print(f"  {r.id:<24}{r.domain:<8}{p['status']:<14}{p['strategy']:<16}"
              f"{str(p['fanout']):<7}{r.snapshot_state}{flag}")

    if rep["snapshot"]["changed"]:
        print(f"\n⚠ SNAPSHOTS MODIFIÉS (dérive du resolver) : {rep['snapshot']['changed']}")
    if rep["snapshot"]["new"]:
        print(f"\nℹ Nouveaux cas sans snapshot : {rep['snapshot']['new']} "
              f"(lancer --update pour les figer)")

    print("\n" + "=" * 64)
    if rep["violations"]:
        print("VIOLATIONS DE SÉCURITÉ ANALYTIQUE (ÉLIMINATOIRE) :")
        for cid, v in rep["violations"]:
            print(f"  ✗ {cid} : {v}")
        return 1
    print("Sécurité analytique : AUCUNE violation ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

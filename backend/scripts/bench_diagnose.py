#!/usr/bin/env python3
"""Phase 2 — C3b : diagnostic « attendu vs produit » d'un rapport de benchmark.

Pour chaque cas où le modèle PRINCIPAL a été pénalisé (rappel < 1, objectif
principal « oublié », ou « substitution silencieuse »), affiche côte à côte :
  - les types d'objectifs qu'on ATTENDAIT (corpus) ;
  - le type principal PRODUIT et l'ensemble des types produits.

But : distinguer une vraie faute du modèle d'un simple DÉSACCORD D'ÉTIQUETTE
entre le corpus et une interprétation raisonnable (ex. « CA par produit et
région » étiqueté `attribution` mais produit `aggregate`). N'appelle aucun modèle.

Usage :
  python scripts/bench_diagnose.py                 # ./bench_report.json
  python scripts/bench_diagnose.py bench_smoke.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.eval_cases import CASES_BY_ID  # noqa: E402


def _flags(c: dict) -> str:
    out = []
    if c.get("semantic") is False:
        out.append("HORS-DOMAINE (conformité seule)")
    if c.get("primary_forgotten"):
        out.append("principal_oublié")
    if c.get("silent_substitution"):
        out.append("SUBSTITUTION")
    if c.get("out_of_catalog"):
        out.append("hors_catalogue")
    if not c.get("json_ok", True):
        out.append(f"non_conforme({c.get('error')})")
    return ",".join(out) or "-"


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("bench_report.json")
    if not path.is_file():
        print(f"ERREUR : rapport introuvable : {path}", file=sys.stderr)
        return 2
    report = json.loads(path.read_text(encoding="utf-8"))

    for cat_name, block in (report.get("catalogs") or {}).items():
        main_rep = block.get("main") or {}
        # dédup par cas (le rapport agrège plusieurs runs) : on garde la 1re occurrence pénalisée
        seen: dict[str, dict] = {}
        for c in main_rep.get("cases") or []:
            cid = c.get("case_id")
            penalised = (not c.get("json_ok", True) or c.get("recall", 1.0) < 1.0
                         or c.get("primary_forgotten") or c.get("silent_substitution")
                         or c.get("out_of_catalog"))
            if penalised and cid not in seen:
                seen[cid] = c
        if not seen:
            print(f"\n[{cat_name}] modèle principal : aucun cas pénalisé ✔")
            continue
        print(f"\n[{cat_name}] {len(seen)} cas pénalisés (modèle principal) :")
        print(f"  {'cas':<22} {'attendu (+accept)':<34} {'produit':<30} flags")
        for cid, c in sorted(seen.items()):
            case = CASES_BY_ID.get(cid)
            expected = ",".join(sorted(case.expect_types)) if case else "?"
            accept = ",".join(sorted(getattr(case, "accept_types", ()))) if case else ""
            exp_col = expected + (f" (+{accept})" if accept else "")
            produced = ",".join(c.get("produced_types") or [])
            print(f"  {cid:<22} {exp_col:<34} {produced:<30} {_flags(c)}")
    print("\nLecture : si « produit » est un type sensé mais ≠ « attendu », c'est un "
          "désaccord d'ÉTIQUETTE (corpus/scoring), pas une faute du modèle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

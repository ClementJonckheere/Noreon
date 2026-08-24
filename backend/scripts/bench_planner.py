#!/usr/bin/env python3
"""Phase 2 — C3b : benchmark comparatif des modèles de planification (OVHcloud).

Exécuté par l'OPÉRATEUR avec sa clé (jamais dans le dépôt). Compare deux modèles
sur le corpus × plusieurs catalogues versionnés, avec DEUX tables de qualification :

  - modèle principal (ex. gpt-oss-120b) : évaluation SÉMANTIQUE sur tout le corpus ;
  - modèle simple (ex. gpt-oss-20b) : évaluation sémantique UNIQUEMENT sur les cas
    `simple_eligible`, avec le principal comme référence sur ce sous-ensemble ; sur
    les autres cas, seule la conformité JSON est mesurée + on vérifie que le
    pré-routeur les aurait EXCLUS du 20b.

Le routage de PRODUCTION reste désactivé : ce script sert à décider.

Exemple :
  NOREON_OVH_BASE_URL=https://oai.endpoints.kepler.ai.cloud.ovh.net/v1 \\
  OVH_AI_ENDPOINTS_ACCESS_TOKEN=*** \\
  python scripts/bench_planner.py --main gpt-oss-120b --simple gpt-oss-20b \\
      --catalog retail_full --catalog crm --runs 2 --out bench.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis import benchmark as B                       # noqa: E402
from app.analysis.catalogs import load_catalog, list_catalogs  # noqa: E402
from app.analysis.contracts import ContractError, validate_interpretation  # noqa: E402
from app.analysis.eval_cases import CASES, DEVELOPMENT, HOLDOUT  # noqa: E402
from app.analysis.interpreter import PLANNER_SYSTEM, build_user_prompt  # noqa: E402
from app.analysis.planner_privacy import sanitize_question  # noqa: E402
from app.analysis.schema_models import interpretation_json_schema  # noqa: E402
from app.llm.providers import OVHcloudProvider, PlannerConfigError  # noqa: E402

_TOKEN_ENV = "OVH_AI_ENDPOINTS_ACCESS_TOKEN"


def _load_dotenv(*, override: bool = False) -> str | None:
    """Charge un `.env` (léger, sans dépendance) s'il existe.

    Cherche `backend/.env` puis la racine du dépôt. Les variables déjà définies
    dans le shell gagnent (override=False) : `$env:VAR` reste prioritaire. Ne lit
    QUE des `CLE=valeur` simples, ignore commentaires et lignes vides. Le vrai
    `.env` est gitignoré — jamais de clé dans le dépôt.
    """
    here = Path(__file__).resolve()
    for candidate in (here.parents[1] / ".env", here.parents[2] / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and (override or key not in os.environ):
                os.environ[key] = val
        return str(candidate)
    return None


def _provider(model: str) -> OVHcloudProvider:
    base = os.getenv("NOREON_OVH_BASE_URL", "")
    token = os.getenv(_TOKEN_ENV, "")
    missing = [n for n, v in (("NOREON_OVH_BASE_URL", base), (_TOKEN_ENV, token)) if not v]
    if missing:
        raise PlannerConfigError("Config OVHcloud incomplète : " + ", ".join(missing))
    return OVHcloudProvider(model=model, api_key=token, base_url=base)


def _make_plan_fn(provider: OVHcloudProvider, attempts: int):
    schema = interpretation_json_schema()

    def plan_fn(model: str, question: str, catalog) -> B.PlanResult:
        safe_q, _ = sanitize_question(question)
        user = build_user_prompt(catalog, safe_q)
        last_kind = "network"
        for i in range(1, attempts + 1):
            t0 = time.perf_counter()
            try:
                raw = provider.plan(system=PLANNER_SYSTEM, user=user, json_schema=schema)
            except Exception:  # noqa: BLE001 - incident réseau/HTTP
                last_kind = "network"
                continue
            latency = (time.perf_counter() - t0) * 1000
            try:
                interp = validate_interpretation(json.loads(raw))
            except (ContractError, json.JSONDecodeError):
                last_kind = "contract"
                continue
            tokens = getattr(provider, "last_usage", None)
            return B.PlanResult(interp=interp, error_kind="none", latency_ms=round(latency, 1),
                                tokens=(tokens or {}).get("total_tokens") if tokens else None,
                                attempts=i)
        return B.PlanResult(interp=None, error_kind=last_kind, attempts=attempts)

    return plan_fn


def _agreement_on_simple(simple_rep: B.ModelReport, main_rep: B.ModelReport) -> float:
    """Accord 20b/120b sur les cas simples : même conclusion (JSON conforme + rappel plein)."""
    by_id = {r.case_id: r for r in main_rep.results}
    pairs = [(r, by_id.get(r.case_id)) for r in simple_rep.results if r.semantic and r.json_ok]
    if not pairs:
        return 0.0
    agree = sum(1 for s, m in pairs if m and m.json_ok and abs(s.recall - m.recall) < 1e-9
                and not s.out_of_catalog)
    return agree / len(pairs)


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark des modèles de planification (OVHcloud).")
    ap.add_argument("--main", required=True, help="modèle principal (toutes demandes)")
    ap.add_argument("--simple", required=True, help="modèle simple (sous-ensemble strict)")
    ap.add_argument("--catalog", action="append", default=[], help="nom/chemin (répétable)")
    ap.add_argument("--runs", type=int, default=2, help="exécutions par modèle (défaut 2)")
    ap.add_argument("--attempts", type=int, default=2, help="tentatives JSON par appel")
    ap.add_argument("--split", choices=["all", "development", "holdout"], default="all")
    ap.add_argument("--out", default="bench_report.json")
    args = ap.parse_args()

    loaded = _load_dotenv()
    if loaded:
        print(f".env chargé : {loaded} (les variables du shell restent prioritaires)")

    cases = {"all": CASES, "development": DEVELOPMENT, "holdout": HOLDOUT}[args.split]
    catalogs = args.catalog or ["retail_full"]
    print(f"Corpus : {len(cases)} cas ({args.split}) · catalogues : {catalogs} · "
          f"runs : {args.runs} · disponibles : {list_catalogs()}")

    try:
        main_provider = _provider(args.main)
        simple_provider = _provider(args.simple)
    except PlannerConfigError as e:
        print(f"ERREUR : {e}", file=sys.stderr)
        return 2

    # Préflight : disponibilité + support json_schema.
    for label, prov in (("principal", main_provider), ("simple", simple_provider)):
        pf = B.preflight(prov)
        print(f"Préflight {label} ({prov.model}) : {pf}")
        if not pf["ok"]:
            print(f"ERREUR : modèle {prov.model} indisponible ou sans json_schema.", file=sys.stderr)
            return 3

    report = {"main_model": args.main, "simple_model": args.simple, "split": args.split,
              "runs": args.runs, "catalogs": {}}
    for cat_name in catalogs:
        catalog = load_catalog(cat_name)
        main_reps, simple_reps = [], []
        for _ in range(args.runs):
            main_reps.append(B.run_model(args.main, cases, catalog,
                                         plan_fn=_make_plan_fn(main_provider, args.attempts),
                                         tier="main"))
            simple_reps.append(B.run_model(args.simple, cases, catalog,
                                           plan_fn=_make_plan_fn(simple_provider, args.attempts),
                                           tier="simple", main_model=args.main, simple_model=args.simple))
        main_rep = _merge(main_reps)
        simple_rep = _merge(simple_reps)
        agreement = _agreement_on_simple(simple_rep, main_rep)
        report["catalogs"][cat_name] = {
            "main": main_rep.as_dict(),
            "simple": simple_rep.as_dict(),
            "agreement_20b_vs_120b_on_simple": round(agreement, 4),
        }
        print(f"\n[{cat_name}] principal {args.main} : "
              f"{'ÉLIMINÉ' if main_rep.eliminated else 'qualifié'} "
              f"({main_rep.elimination_reasons() or 'OK'})")
        print(f"[{cat_name}] simple {args.simple} (sous-ensemble simple) : "
              f"{'ÉLIMINÉ' if simple_rep.eliminated else 'qualifié'} "
              f"({simple_rep.elimination_reasons() or 'OK'}) · accord vs principal {agreement:.0%}")

    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRapport écrit : {args.out}")
    print("Routage de production TOUJOURS désactivé — sélection des modèles à décider manuellement.")
    return 0


def _merge(reps: list[B.ModelReport]) -> B.ModelReport:
    """Concatène les runs d'un même modèle en un seul rapport (100 sorties = 50×2)."""
    merged = B.ModelReport(model=reps[0].model, tier=reps[0].tier)
    for r in reps:
        merged.results.extend(r.results)
    return merged


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Phase 2 — shadow : campagne d'injection de questions vers l'API chat.

Envoie ~30-50 questions (4 familles : simples, multi-objectifs, ambiguës,
impossibles) à `POST /connections/{id}/chat`. Chaque réponse déclenche
l'observation shadow (mode `shadow`), qui écrit dans `planner_shadow_evaluations`.
Analyser ensuite avec `scripts/shadow_report.py`.

Prérequis : l'API Noreon tourne, `PLANNER_MODE=shadow`, config OVH en place, et la
connexion ciblée a un schéma scanné.

  python scripts/shadow_campaign.py --connection-id 1 --tenant demo
  python scripts/shadow_campaign.py --connection-id 1 --questions-file mes_questions.txt
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

# 4 familles. Génériques : adapte-les à TON schéma avec --questions-file si besoin.
SIMPLE = [
    "Combien de clients ai-je ?", "Nombre de commandes au total",
    "Chiffre d'affaires total", "Panier moyen", "Top 10 des clients par chiffre d'affaires",
    "Classement des produits par montant vendu", "Combien de produits au catalogue",
    "Montant total facturé", "Nombre de factures émises", "Combien de commandes par mois",
]
MULTI = [
    "Segmente mes clients par valeur et regarde quels produits chaque segment achète",
    "Analyse de cohortes des inscriptions par mois puis la rétention par segment",
    "Répartis le chiffre d'affaires par produit et par région",
    "Fais une segmentation RFM, une analyse de cohortes et un classement des produits",
    "Quels produits sont achetés ensemble et par quel segment de clientèle",
    "Corrélation entre l'ancienneté du compte et sa valeur, puis un classement",
    "Ventes par mois et par catégorie, avec la tendance sur l'année",
    "Répartis mes clients par tranche d'âge et par région",
]
AMBIGUOUS = [
    "Analyse le chiffre d'affaires par segment (HT ou TTC ?)",
    "Analyse la marge par produit (brute ou nette ?)",
    "Montre-moi les meilleurs clients",
    "Quels sont mes produits les plus rentables ?",
    "Comment se portent mes ventes ?",
    "Donne-moi un résumé de l'activité",
]
IMPOSSIBLE = [
    "Prévision des ventes pour le trimestre prochain",
    "Prédire quels clients vont résilier",
    "Pourquoi le chiffre d'affaires baisse-t-il depuis trois mois ?",
    "Quelle météo a le plus d'impact sur mes ventes ?",
    "Compare mes prix à ceux de mes concurrents",
    "Quel sera mon chiffre d'affaires l'an prochain ?",
    "Analyse le sentiment des avis clients",
    "Quel est le taux de satisfaction par vendeur ?",
]


def _questions(path: str | None) -> list[tuple[str, str]]:
    if path:
        lines = [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]
        return [("custom", q) for q in lines]
    out = []
    for fam, qs in (("simple", SIMPLE), ("multi", MULTI), ("ambiguous", AMBIGUOUS), ("impossible", IMPOSSIBLE)):
        out += [(fam, q) for q in qs]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--connection-id", type=int, required=True)
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--tenant", default=None, help="header X-Tenant (repli dev)")
    ap.add_argument("--token", default=None, help="Bearer token (si auth activée)")
    ap.add_argument("--delay", type=float, default=1.0, help="pause entre requêtes (s)")
    ap.add_argument("--questions-file", default=None)
    ap.add_argument("--no-deep", action="store_true", help="désactive l'analyse profonde")
    args = ap.parse_args()

    qs = _questions(args.questions_file)
    url = f"{args.base_url.rstrip('/')}/connections/{args.connection_id}/chat"
    headers = {}
    if args.tenant:
        headers["X-Tenant"] = args.tenant
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    print(f"Campagne shadow → {url} · {len(qs)} questions · délai {args.delay}s")
    ok = 0
    with httpx.Client(timeout=120.0) as client:
        for i, (fam, q) in enumerate(qs, 1):
            try:
                r = client.post(url, headers=headers,
                                json={"question": q, "run_analysis": True, "deep_analysis": not args.no_deep})
                status = r.json().get("status") if r.status_code == 200 else f"HTTP {r.status_code}"
                ok += r.status_code == 200
                print(f"  [{i:>2}/{len(qs)}] {fam:<11} {status:<14} · {q[:52]}")
            except Exception as exc:  # noqa: BLE001
                print(f"  [{i:>2}/{len(qs)}] {fam:<11} ERREUR {type(exc).__name__} · {q[:52]}")
            time.sleep(args.delay)

    print(f"\n{ok}/{len(qs)} réponses OK. Les observations shadow s'écrivent en tâche de fond.")
    print("Patiente ~10 s puis : python scripts/shadow_report.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

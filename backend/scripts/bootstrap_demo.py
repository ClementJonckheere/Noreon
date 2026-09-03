#!/usr/bin/env python3
"""Setup EN UNE COMMANDE d'une base de démo + connexion Noreon scannée.

Prépare tout ce qu'il faut pour la campagne shadow :
  1. crée la base `noreon_demo` (retail : stores/customers/products/orders/
     order_items/payments — vrai 1→n orders→order_items pour l'anti-fanout) ;
  2. charge `scripts/seed_demo.sql` ;
  3. crée un rôle READ-ONLY (`noreon_ro`/`readonly`) ;
  4. crée la connexion Noreon via l'API + la SCANNE ;
  5. affiche le connection_id et la commande de campagne.

Prérequis : l'API tourne (uvicorn), Postgres accessible (Docker exposé sur
localhost:5432). Idempotent : relançable sans casse.

  python scripts/bootstrap_demo.py --tenant demo
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
import psycopg

_SEED = Path(__file__).resolve().parents[2] / "scripts" / "seed_demo.sql"


def _admin(dsn: str):
    return psycopg.connect(dsn, autocommit=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url", default="http://localhost:8000")
    ap.add_argument("--tenant", default="demo")
    ap.add_argument("--pg-host", default="localhost")
    ap.add_argument("--pg-port", type=int, default=5432)
    ap.add_argument("--admin-user", default="noreon")
    ap.add_argument("--admin-pass", default="noreon")
    ap.add_argument("--demo-db", default="noreon_demo")
    ap.add_argument("--ro-user", default="noreon_ro")
    ap.add_argument("--ro-pass", default="readonly")
    args = ap.parse_args()

    if not _SEED.is_file():
        print(f"ERREUR : seed introuvable : {_SEED}", file=sys.stderr)
        return 2
    base = f"postgresql://{args.admin_user}:{args.admin_pass}@{args.pg_host}:{args.pg_port}"

    # 1) base démo
    print(f"1. Base {args.demo_db} …")
    with _admin(f"{base}/postgres") as adm:
        exists = adm.execute("SELECT 1 FROM pg_database WHERE datname=%s", (args.demo_db,)).fetchone()
        if not exists:
            adm.execute(f'CREATE DATABASE "{args.demo_db}"')
            print("   créée.")
        else:
            print("   existe déjà.")

    # 2) seed
    print("2. Chargement du seed retail …")
    with _admin(f"{base}/{args.demo_db}") as db:
        db.execute(_SEED.read_text(encoding="utf-8"))
    print("   ok (stores/customers/products/orders/order_items/payments).")

    # 3) rôle read-only
    print(f"3. Rôle read-only {args.ro_user} …")
    with _admin(f"{base}/postgres") as adm:
        if not adm.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (args.ro_user,)).fetchone():
            adm.execute(f"CREATE ROLE \"{args.ro_user}\" LOGIN PASSWORD '{args.ro_pass}'")
        adm.execute(f'GRANT CONNECT ON DATABASE "{args.demo_db}" TO "{args.ro_user}"')
    with _admin(f"{base}/{args.demo_db}") as db:
        db.execute(f'GRANT USAGE ON SCHEMA public TO "{args.ro_user}"')
        db.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{args.ro_user}"')
        db.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO "{args.ro_user}"')
    print("   ok (SELECT seul).")

    # 4) connexion Noreon + scan (via API)
    print("4. Création de la connexion Noreon + scan …")
    headers = {"X-Tenant": args.tenant}
    payload = {"name": "Démo Retail", "engine": "postgresql", "host": args.pg_host,
               "port": args.pg_port, "database": args.demo_db,
               "username": args.ro_user, "password": args.ro_pass}
    with httpx.Client(timeout=60.0) as c:
        try:
            c.get(f"{args.api_url}/connections", headers=headers)   # préflight : l'API est-elle là ?
        except httpx.ConnectError:
            print(f"\nERREUR : l'API Noreon n'est pas joignable sur {args.api_url}.\n"
                  "   Ouvre un AUTRE terminal, va dans backend/ et lance (laisse-le tourner) :\n"
                  "     python -m uvicorn app.main:app --port 8000\n"
                  "   puis relance ce bootstrap (il reprendra à l'étape 4 — la base est déjà prête).",
                  file=sys.stderr)
            return 5
        r = c.post(f"{args.api_url}/connections", headers=headers, json=payload)
        if r.status_code >= 300:
            print(f"ERREUR création connexion : HTTP {r.status_code} · {r.text[:300]}", file=sys.stderr)
            return 3
        body = r.json()
        cid = body["connection"]["id"]
        ro = (body.get("probe") or {}).get("read_only")
        print(f"   connexion #{cid} créée (read_only={ro}).")
        if ro is False:
            print("   ⚠ non read-only → le scan sera refusé. Vérifie les droits du rôle.", file=sys.stderr)
        s = c.post(f"{args.api_url}/connections/{cid}/scan", headers=headers)
        if s.status_code >= 300:
            print(f"ERREUR scan : HTTP {s.status_code} · {s.text[:300]}", file=sys.stderr)
            return 4
        snap = s.json()
        print(f"   scan ok : snapshot v{snap.get('version')} · id {snap.get('snapshot_id')}.")

    print("\n✅ Prêt. Lance la campagne shadow :")
    print(f"   python scripts/shadow_campaign.py --connection-id {cid} --tenant {args.tenant} --delay 1")
    print("   (puis, ~10 s après)  python scripts/shadow_report.py --limit 200")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

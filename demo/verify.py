#!/usr/bin/env python3
"""Runner de vérification d'un scénario de la bibliothèque de démonstration.

Branche Noreon sur la base source du scénario (lecture seule), rejoue le pipeline
complet — Discover (scan) → Understand (profil) → Reason (investigation) → Reveal
(réponse) — et imprime ce que le moteur PRODUIT RÉELLEMENT, pour le comparer au
Gold Standard écrit à la main (demo/<scenario>/gold_standard.md).

    cd backend && python ../demo/verify.py retail

Ne modifie jamais la base source ; la base interne est utilisée en transaction
puis annulée (rollback), rien n'est persisté.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permet « python ../demo/verify.py » depuis backend/ comme depuis la racine.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.core.db import SessionLocal  # noqa: E402
from app.models.schema_catalog import DbColumn  # noqa: E402
from app.models.tenant import Tenant, TenantSettings  # noqa: E402
from app.services import chat as chat_svc  # noqa: E402
from app.services import connections as conn_svc  # noqa: E402
from app.services import scanner  # noqa: E402
from app.services.profiler import persist_profiles, profile_table  # noqa: E402
from app.services.schema_context import current_snapshot  # noqa: E402
from sqlalchemy import select  # noqa: E402

SCENARIO_QUESTIONS = {
    "retail": "Pourquoi le chiffre d'affaires baisse-t-il depuis 4 mois ?",
    "crm": "Pourquoi le churn augmente-t-il ?",
    "finance": "Pourquoi la marge diminue-t-elle ?",
    "supply_chain": "Pourquoi les ruptures de stock augmentent-elles ?",
    "hr": "Pourquoi les départs augmentent-ils ?",
}


def _bar(title: str) -> None:
    print("\n" + "═" * 78 + f"\n {title}\n" + "═" * 78)


def main(scenario: str) -> None:
    question = SCENARIO_QUESTIONS.get(scenario)
    if question is None:
        print(f"Scénario inconnu : {scenario}. Connus : {', '.join(SCENARIO_QUESTIONS)}")
        sys.exit(1)

    db = SessionLocal()
    try:
        tenant = Tenant(slug=f"demo-{scenario}", name=f"Demo {scenario}")
        tenant.settings = TenantSettings(tenant=tenant)
        db.add(tenant)
        db.flush()

        conn, probe = conn_svc.create_connection(
            db, tenant_id=tenant.id, name=f"demo-{scenario}", host="localhost", port=5432,
            database=f"noreon_demo_{scenario}", username="noreon_ro", password="readonly",
        )
        db.flush()
        adapter = conn_svc.get_source_adapter(conn)

        _bar("DISCOVER — connexion & lecture seule")
        print(f"Base source : noreon_demo_{scenario}")
        detail = probe.get("detail", "") if isinstance(probe, dict) else getattr(probe, "detail", "")
        print(f"Lecture seule vérifiée : {conn.is_read_only}  ({detail})")

        scanner.scan_and_persist(db, conn, adapter)
        snapshot = current_snapshot(db, conn.id)
        print(f"Tables détectées : {len([t for t in snapshot.tables if t.table_type == 'table'])}")
        rels = snapshot.relations
        print(f"Relations (dont FK implicites) : {len(rels)}")

        _bar("UNDERSTAND — profilage")
        for t in snapshot.tables:
            if t.table_type != "table":
                continue
            cols = db.execute(
                select(DbColumn).where(DbColumn.table_id == t.id).order_by(DbColumn.ordinal)
            ).scalars().all()
            persist_profiles(db, conn, t, profile_table(adapter, t, cols))
        print("Profils échantillonnés persistés.")

        _bar(f"REASON + REVEAL — « {question} »")
        r = chat_svc.answer_question(db, conn, question, run_analysis=True, deep_analysis=True)

        print(f"Statut          : {r.status}")
        print(f"Intention       : {r.intent}  →  {r.intent_restated}")
        print(f"\nMessage :\n{r.message}")

        inv = r.investigation
        if inv:
            print(f"\nSujet / mesure  : {inv['subject']} · {inv['metric_label']}")
            if r.chronicle:
                print(f"\nChronologie     : {r.chronicle['narrative']}")
            print("\nFacteurs dominants (drivers) :")
            for d in inv.get("drivers_struct", []):
                print(f"  • {d['dimension']} → « {d['segment']} » : {d['share']}%")
            if inv.get("revisions"):
                print("\nChangement d'avis :")
                for rev in inv["revisions"]:
                    print(f"  ↻ {rev}")
            print(f"\nConclusion      : {inv.get('conclusion', '')}")

        if r.self_critique:
            print("\nAuto-critique (ce qui pourrait remettre en cause la conclusion) :")
            for c in r.self_critique:
                print(f"  ⚖ Cette analyse {c}.")

        if r.decisions:
            print("\nDecision Engine :")
            print(f"  Objectif reformulé : {r.decisions['restated']}")
            for x in r.decisions["decisions"]:
                imp = f" · impact {x['impact']}" if x.get("impact") else ""
                print(f"  {'★'*x.get('stars',3)} {x['role']} — {x['recommendation']}{imp}")
            if r.decisions.get("inaction"):
                print(f"  ⏳ Inaction : {r.decisions['inaction']}")

        if r.serendipity:
            print(f"\nSérendipité     : {r.serendipity['title']} — {r.serendipity['detail']}")

        if r.confidence:
            print(f"\nConfiance       : {r.confidence.get('score')} / 100")
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "retail")

"""Rapports auto-critiques — « ce qui pourrait remettre en question cette conclusion ».

Très peu d'outils osent afficher leurs propres angles morts. Noreon le fait : à
la fin d'une analyse, il liste honnêtement les hypothèses implicites et les
limites qui pourraient invalider la conclusion — fondées sur des signaux réels du
schéma, pas sur des généralités.

Exemples :
  • suppose que les commandes annulées sont exclues (colonne de statut non filtrée) ;
  • suppose que les magasins de test sont correctement écartés ;
  • suppose qu'aucune promotion exceptionnelle n'a faussé la période.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.schema_catalog import DbColumn, DbTable, SchemaSnapshot

_STATUS_RE = re.compile(r"statut|status|etat|state|annul|cancel|is_valid|valide", re.I)
_TEST_RE = re.compile(r"\btest\b|demo|sandbox|factice|fictif", re.I)
_REVENUE_RE = re.compile(r"ca\b|chiffre|revenu|revenue|montant|amount|ventes?|sales?", re.I)


def build(
    db: Session, conn, *, question: str, sql: str,
    tables_used: list[str], has_time_series: bool,
    assumptions: list[str], company_conventions: list[str] | None,
    measure_options: dict | None, sampled: bool, truncated: bool,
) -> list[str]:
    caveats: list[str] = []
    table_names = [t.split(".")[-1].lower() for t in (tables_used or [])]
    sql_l = (sql or "").lower()

    snapshot = db.execute(
        select(SchemaSnapshot).where(
            SchemaSnapshot.connection_id == conn.id, SchemaSnapshot.is_current.is_(True)
        )
    ).scalar_one_or_none()
    cols_by_table: dict[str, list[str]] = {}
    if snapshot is not None and table_names:
        rows = db.execute(
            select(DbTable.table_name, DbColumn.name)
            .join(DbColumn, DbColumn.table_id == DbTable.id)
            .where(DbTable.snapshot_id == snapshot.id)
        ).all()
        for t, c in rows:
            cols_by_table.setdefault(t.lower(), []).append(c)

    # 1) Commandes annulées / lignes non valides : une colonne de statut existe
    #    sur une table utilisée mais n'est pas filtrée dans la requête.
    for t in table_names:
        status_cols = [c for c in cols_by_table.get(t, []) if _STATUS_RE.search(c)]
        unfiltered = [c for c in status_cols if c.lower() not in sql_l]
        if unfiltered:
            caveats.append(
                f"suppose que les lignes non valides/annulées sont à exclure "
                f"(colonne « {unfiltered[0]} » de « {t} » non filtrée)"
            )
            break

    # 2) Magasins / entités de test : soit une colonne « test », soit une
    #    convention d'entreprise à ce sujet.
    test_cols = [(t, c) for t, cs in cols_by_table.items() for c in cs
                 if t in table_names and _TEST_RE.search(c)]
    conv_test = any(_TEST_RE.search(c) for c in (company_conventions or []))
    if test_cols:
        t, c = test_cols[0]
        caveats.append(f"suppose que les entités de test sont correctement identifiées "
                       f"(colonne « {c} » de « {t} »)")
    elif conv_test:
        caveats.append("suppose que les magasins/entités de test sont correctement écartés "
                       "(convention d'entreprise appliquée)")
    elif any(re.search(r"store|magasin|shop|boutique", t) for t in table_names):
        caveats.append("suppose qu'aucun magasin de test ne fausse les totaux "
                       "(aucun indicateur de test détecté)")

    # 3) Promotion exceptionnelle : pertinent pour une mesure de revenu dans le temps.
    if has_time_series and (_REVENUE_RE.search(question) or (measure_options is not None)):
        caveats.append("suppose qu'aucune promotion ou événement exceptionnel n'a faussé la période")

    # 4) Base monétaire (HT vs TTC) : un autre choix donnerait un total différent.
    if measure_options is not None:
        kind = measure_options.get("chosen_kind")
        base = f" ({kind})" if kind else ""
        caveats.append(f"repose sur la mesure « {measure_options.get('chosen')} »{base} : "
                       "une autre base (HT/TTC) donnerait un total différent")

    # 5) Récence de la dernière période : souvent incomplète.
    if has_time_series:
        caveats.append("la période la plus récente peut être incomplète (données encore en cours)")

    # 6) Couverture partielle.
    if sampled:
        caveats.append("s'appuie sur un échantillon, pas sur l'intégralité des données")
    if truncated:
        caveats.append("porte sur un résultat tronqué par la limite automatique")

    # 7) Hypothèses du moteur SQL restées implicites (dédupliquées).
    for a in (assumptions or []):
        short = a.rstrip(".")
        if short and short.lower() not in " ".join(caveats).lower():
            caveats.append(f"repose sur : {short[0].lower()}{short[1:]}")

    return caveats[:6]

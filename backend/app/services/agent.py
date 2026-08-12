"""Moteur de raisonnement (agent d'investigation).

Pour une question ouverte (« pourquoi les ventes baissent ? »), un simple
NL→SQL ne suffit pas. L'agent :

    Question → Planification → Sous-questions → Exécution → Synthèse

1. **Planifie** : à partir du sujet (table de faits + mesure) et de ses
   dimensions, il déclare ce qu'il va examiner (tendance, magasins, produits,
   clients, saisonnalité…), avec une justification par étape.
2. **Exécute** chaque sous-question par une agrégation en lecture seule
   (mêmes garde-fous), et en extrait un enseignement chiffré.
3. **Synthétise** : classe les facteurs, conclut, recommande.

Hors-ligne et auditable : chaque étape porte SON SQL et SON constat. Respecte la
gouvernance d'espace (tables/colonnes masquées écartées du raisonnement).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.services.deep_analysis import (
    _candidate_dimensions,
    _date_bucket,
    _fmt,
    _load_schema,
    _num,
    _pick_fact_table,
    _pick_measure,
    _q,
    _run_segmentation,
)

log = get_logger("noreon.agent")

# Intentions « analytiques » qui déclenchent une investigation plutôt qu'un
# simple SQL.
_INVESTIGATE_RE = re.compile(
    r"\b(pourquoi|why|explique|expliqu|analyse|analyser|comprendre|comprends|"
    r"cause|causes|raison|raisons|driver|facteur|facteurs|diagnos|"
    r"baisse|baisser|hausse|chute|chuter|recul|recule|progress|"
    r"evolue|evolu|évolu|tendance|tendances|se passe|qu'?est[- ]ce qui)\b",
    re.IGNORECASE,
)

_MAX_DIM_STEPS = 5

# Vocabulaire métier → racine de table : oriente le SUJET selon la question
# (« ventes » vise les commandes, pas les lignes de commande).
_TABLE_SYNONYMS = {
    "orders": {"vente", "ventes", "sale", "sales", "commande", "commandes",
               "order", "orders", "ca", "chiffre", "revenu", "revenue", "panier"},
    "customers": {"client", "clients", "customer", "customers", "acheteur", "acheteurs"},
    "products": {"produit", "produits", "product", "products", "article", "articles", "gamme"},
    "stores": {"magasin", "magasins", "store", "stores", "boutique", "boutiques"},
    "payments": {"paiement", "paiements", "payment", "payments"},
}


def should_investigate(question: str) -> bool:
    return bool(_INVESTIGATE_RE.search(question))


def _pick_subject(schema, question: str, allowed: list[str]):
    """Table de faits guidée par la question, à défaut par la topologie."""
    tokens = set(re.findall(r"[a-zà-ÿ0-9_]+", question.lower()))
    best, best_score = None, 0
    for name in allowed:
        t = schema.tables.get(name)
        if t is None:
            continue
        syns = _TABLE_SYNONYMS.get(t.name.lower(), set()) | {t.name.lower(), t.name.lower().rstrip("s")}
        score = len(tokens & syns)
        if score > best_score:
            best, best_score = t, score
    if best is not None:
        return best
    return _pick_fact_table(schema, allowed)


@dataclass
class Step:
    title: str
    question: str
    rationale: str
    sql: str
    finding: str
    figures: list = field(default_factory=list)


@dataclass
class Investigation:
    question: str
    subject: str
    metric_label: str
    plan: list[dict] = field(default_factory=list)          # {title, rationale}
    steps: list[dict] = field(default_factory=list)
    key_drivers: list[str] = field(default_factory=list)
    # Facteurs dominants structurés (pour le Decision Engine) :
    # {dimension, segment, share}.
    drivers_struct: list[dict] = field(default_factory=list)
    # Attribution de la VARIATION (contribution à la baisse/hausse, pas part du
    # total) : {dimension, segment, contribution_pct, lift, recent, prior, window}.
    attribution: dict | None = None
    # Causes MULTIPLES : plusieurs foyers concentrés se partagent la variation
    # (ex. trois magasins à 40/35/25 %). Liste de {segment, contribution_pct, …}.
    multi_causes: list[dict] = field(default_factory=list)
    # Variation GÉNÉRALISÉE : tendance nette mais aucun segment disproportionné
    # (cause transverse probable — prix, saison, macro).
    broad_based: bool = False
    # SAISONNALITÉ : la baisse des derniers mois est conforme à la même période
    # l'an dernier → normale, pas une anomalie.
    seasonal: bool = False
    seasonal_detail: str = ""
    # HUMILITÉ : données trop incomplètes/douteuses pour conclure avec confiance.
    low_quality: bool = False
    quality_detail: str = ""
    conclusion: str = ""
    recommendations: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    # Données de tendance (pour un graphique dans la réponse).
    trend_columns: list[str] = field(default_factory=list)
    trend_rows: list[list] = field(default_factory=list)
    # Journal de raisonnement (pour les experts) : chaque étape horodatée, avec
    # les analyses ESSAYÉES, REJETÉES et RETENUES.
    journal: list[dict] = field(default_factory=list)       # {t, phase, detail, status}
    # « Le moteur change d'avis » : hypothèse initiale vs. ce que disent les données.
    revisions: list[str] = field(default_factory=list)
    # VÉRIFICATION AUTOMATIQUE : ce qui a été testé et pourquoi une piste a été
    # écartée — factuel et chiffré, pas un journal introspectif.
    # {text, winner:{dimension,segment,pct}, tested:[{dimension,segment,pct}]}
    verification: dict | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _initial_hypothesis(dims: list) -> object | None:
    """Ce qu'un analyste supposerait a priori — souvent la fidélité, sinon le
    premier axe candidat. Sert de point de comparaison pour l'auto-révision."""
    for d in dims:
        if re.search(r"loyal|fidel|fidél", d.label, re.IGNORECASE):
            return d
    return dims[0] if dims else None


def _dim_rationale(label: str) -> str:
    l = label.lower()
    if "age" in l:
        return "L'âge de la clientèle change souvent le comportement d'achat."
    if "city" in l or "ville" in l or "region" in l:
        return "Une zone géographique peut porter seule la variation."
    if "store" in l or "magasin" in l:
        return "Un magasin en difficulté peut expliquer l'ensemble."
    if "categor" in l or "product" in l or "produit" in l:
        return "Une gamme de produits peut tirer le résultat."
    if "loyalty" in l or "fidel" in l:
        return "La fidélité distingue les clients à forte valeur."
    if "method" in l or "paiement" in l or "payment" in l:
        return "Le canal / moyen de paiement révèle des usages différents."
    if "mois" in l or "date" in l or "month" in l:
        return "La saisonnalité et les à-coups temporels comptent."
    return "Cet axe peut structurer la variation observée."


def _trailing_run(rows: list, trend_dir: str) -> int:
    """Nombre de périodes consécutives, en fin de série, allant dans le sens de la
    tendance (la « fenêtre » de baisse/hausse — « depuis 4 mois »)."""
    want_down = trend_dir == "baisse"
    w = 0
    for i in range(len(rows) - 1, 0, -1):
        step_down = rows[i][1] < rows[i - 1][1]
        if step_down == want_down:
            w += 1
        else:
            break
    return w


def _attribute_variation(adapter, conn_id: int, guard_args: dict, fact, dims,
                         measure_sql: str | None, date_col, recent_labels: list[str],
                         prior_labels: list[str], trend_dir: str) -> dict | None:
    """Attribue la VARIATION (fenêtre récente vs précédente) à un segment.

    À la différence de la segmentation (part du *total*), on mesure ici la
    **contribution à la baisse/hausse** : quel segment porte le plus le
    changement. C'est la question de l'analyste senior — « d'où vient la baisse ? »
    plutôt que « d'où vient le chiffre ? ». Renvoie {"mode": "single"|"multi", …},
    ou None (variation généralisée, aucun segment disproportionné).
    """
    if not measure_sql or not recent_labels or not prior_labels:
        return None
    fa = "f"
    bucket = _date_bucket(adapter, "month", f"{fa}.{_q(adapter, date_col.name)}")

    def _in(labels: list[str]) -> str:
        return ", ".join("'" + str(x).replace("'", "") + "'" for x in labels)

    rec_in, pri_in = _in(recent_labels), _in(prior_labels)
    down = trend_dir == "baisse"
    candidates: list[dict] = []   # une entrée par dimension exploitable
    tested: list[dict] = []       # chaque axe examiné + sa force explicative (audit)

    for dim in dims:
        # Les tranches numériques (« tranche de … ») produisent des libellés de
        # segment bruts (« 0 ») peu parlants pour une cause métier : on les écarte.
        if dim.label.startswith("tranche de"):
            continue
        sql = (
            f"SELECT {dim.expr} AS grp, "
            f"sum(CASE WHEN {bucket} IN ({rec_in}) THEN {measure_sql} ELSE 0 END) AS recent, "
            f"sum(CASE WHEN {bucket} IN ({pri_in}) THEN {measure_sql} ELSE 0 END) AS prior "
            f"FROM {adapter.qualified(fact.schema, fact.name)} {fa}{dim.join_sql} "
            f"WHERE {dim.expr} IS NOT NULL GROUP BY {dim.expr}"
        )
        try:
            res = adapter.run_query(sql, connection_id=conn_id, **guard_args)
        except Exception as exc:  # noqa: BLE001 - une dimension qui échoue est ignorée
            log.info("Attribution ignorée (%s) : %s", dim.label, exc)
            continue
        groups = [(str(r[0]), _num(r[1]), _num(r[2])) for r in res.rows]
        if len(groups) < 2:
            continue
        deltas = [(lbl, rec - pri, rec, pri) for lbl, rec, pri in groups]
        same = [(lbl, d, rec, pri) for lbl, d, rec, pri in deltas
                if (d < 0) == down and abs(d) > 1e-9]
        if not same:
            continue
        gross = sum(abs(d) for _, d, _, _ in same)
        total_prior = sum(max(pri, 0) for _, _, _, pri in deltas)
        if gross < 1e-9:
            continue
        samples = [g[0] for g in groups][:12]
        # Contribution + LIFT de CHAQUE segment (pas seulement le premier).
        # LIFT = sur-représentation dans la variation vs. dans la base : un segment
        # n'est une cause que s'il varie PLUS que sa taille ne le voudrait (≈ 1 =
        # simple effet de taille → tautologie).
        segs = []
        for lbl, d, rec, pri in same:
            share = abs(d) / gross * 100.0
            base_share = (max(pri, 0) / total_prior) if total_prior > 1e-9 else 0.0
            lift = (share / 100.0) / base_share if base_share > 1e-9 else 99.0
            segs.append({"dimension": dim.label, "segment": lbl,
                         "contribution_pct": round(share, 1), "lift": round(lift, 2),
                         "recent": rec, "prior": pri, "samples": samples,
                         "sql": res.guarded_sql, "window": len(recent_labels)})
        segs.sort(key=lambda s: s["contribution_pct"], reverse=True)
        # Trace d'audit : force explicative de CET axe (segment le plus mouvant),
        # qu'il soit retenu ou non → alimente la Vérification automatique.
        tested.append({"dimension": dim.label, "segment": segs[0]["segment"],
                       "pct": round(segs[0]["contribution_pct"])})
        # Segments réellement causals de cette dimension (notables + disproportionnés).
        causal = [s for s in segs if s["contribution_pct"] >= 15 and s["lift"] >= 1.3][:3]
        explained = sum(s["contribution_pct"] for s in causal)
        if not causal or explained < 60:
            continue
        candidates.append({"dimension": dim.label, "causal": causal, "explained": explained,
                           "top": causal[0]["contribution_pct"], "top_lift": causal[0]["lift"]})

    tested.sort(key=lambda t: t["pct"], reverse=True)
    if not candidates:
        return None   # aucune cause exploitable → variation GÉNÉRALISÉE (diffuse)

    # Meilleur axe : rasoir d'Occam — on préfère l'explication la plus CONCENTRÉE
    # (segment le plus fort), puis celle qui explique le plus. Ainsi « une région à
    # 97 % » l'emporte sur « deux villes à 51/46 % » qui décrivent le même fait.
    best = max(candidates, key=lambda c: (c["top"], c["explained"]))
    top = best["causal"][0]
    # Une cause UNIQUE domine si son segment porte ≥ 55 % avec un lift franc.
    if top["contribution_pct"] >= 55 and top["lift"] >= 1.5:
        return {"mode": "single", "best": top, "ranked": [top], "tested": tested}
    # Sinon, plusieurs foyers concentrés se partagent la variation → CAUSES MULTIPLES.
    if len(best["causal"]) >= 2:
        return {"mode": "multi", "dimension": best["dimension"],
                "causes": best["causal"], "explained": round(best["explained"], 1), "tested": tested}
    return {"mode": "single", "best": top, "ranked": [top], "tested": tested}


def run_investigation(
    db: Session, conn, adapter, question: str, *,
    guard_args: dict,
    hidden_tables: set[str] | None = None,
    hidden_columns: set[tuple[str, str]] | None = None,
) -> Investigation | None:
    schema = _load_schema(db, conn.id)
    if schema is None:
        return None

    hidden_tables = {t.lower() for t in (hidden_tables or set())}
    hidden_columns = {(t.lower(), c.lower()) for t, c in (hidden_columns or set())}

    names = [n for n in schema.tables if n.lower() not in hidden_tables]
    fact = _pick_subject(schema, question, names)
    if fact is None or fact.name.lower() in hidden_tables:
        return None

    measure = _pick_measure(adapter, fact, question)
    measure_sql = measure.sql
    metric = measure.label
    noun = measure.noun

    dims = _candidate_dimensions(adapter, schema, fact, measure.column)

    def dim_allowed(d) -> bool:
        base = d.bands["column"] if d.bands else None
        if base and (fact.name.lower(), base.lower()) in hidden_columns:
            return False
        # Dimension d'une table liée : « label (table) » → écarter si masquée.
        if d.join_sql and "(" in d.label:
            tbl = d.label.split("(")[-1].rstrip(")").strip().lower()
            if tbl in hidden_tables:
                return False
        return True

    dims = [d for d in dims if dim_allowed(d)]

    inv = Investigation(question=question, subject=fact.name, metric_label=metric)
    queries: list[str] = []

    # Journal de raisonnement — trace vivante pour les experts.
    inv.journal.append({"t": _now(), "phase": "question", "status": "info",
                        "detail": f"Question reçue : « {question} ». Sujet retenu : {fact.name} "
                                  f"(mesure : {metric})."})
    # Hypothèse initiale (avant de regarder les données) — servira à l'auto-révision.
    initial = _initial_hypothesis(dims)
    if initial is not None:
        inv.journal.append({"t": _now(), "phase": "plan", "status": "info",
                            "detail": f"Hypothèse de départ : « {initial.label} » porte probablement la variation."})

    date_col = next((c for c in fact.columns if c.is_temporal
                     and (fact.name.lower(), c.name.lower()) not in hidden_columns), None)

    # --- Garde-fou HUMILITÉ (P-08) : la donnée est-elle assez fiable pour conclure ?
    # Mieux vaut une abstention honnête qu'une fausse certitude tirée de données
    # trouées. On mesure le taux de valeurs manquantes de la MESURE et de la DATE
    # (issu du profilage) : au-delà d'un seuil, on ne conclut pas.
    def _null_rate(col) -> float:
        p = getattr(col, "profile", None) if col else None
        return p.null_rate if (p and p.null_rate is not None) else 0.0

    measure_col_obj = fact.col(measure.column) if measure.column else None
    _issues = []
    if measure_col_obj is not None and _null_rate(measure_col_obj) >= 0.4:
        _issues.append(f"{measure.column} manquant à {_null_rate(measure_col_obj) * 100:.0f}%")
    if date_col is not None and _null_rate(date_col) >= 0.4:
        _issues.append(f"{date_col.name} manquant à {_null_rate(date_col) * 100:.0f}%")
    if _issues:
        inv.low_quality = True
        inv.quality_detail = (
            "Je ne peux pas conclure avec suffisamment de confiance : la qualité des "
            f"données est insuffisante ({', '.join(_issues)}). Toute tendance ou cause "
            "tirée de ces données serait trompeuse. Priorité : fiabiliser la saisie "
            "(mesure et date) avant d'analyser.")
        inv.conclusion = "Conclusion : " + inv.quality_detail
        inv.plan.append({"title": "Contrôle de fiabilité des données",
                         "rationale": "Vérifier que la mesure et la date sont exploitables avant d'analyser."})
        inv.steps.append(asdict(Step(
            title="Contrôle de fiabilité des données",
            question="Les données sont-elles assez complètes pour conclure ?",
            rationale="On mesure le taux de valeurs manquantes de la mesure et de la date.",
            sql="-- audit de complétude (profilage) --",
            finding=inv.quality_detail,
            figures=[{"label": lbl, "value": 0} for lbl in _issues],
        )))
        inv.journal.append({"t": _now(), "phase": "analysis", "status": "rejected",
                            "detail": f"Abstention (qualité insuffisante) : {', '.join(_issues)}."})
        inv.recommendations.append(
            "Ne pas décider sur ces données : fiabiliser d'abord la saisie de la mesure "
            "et de la date, puis relancer l'analyse.")
        return inv

    # --- Étape tendance (si une date existe sur la table de faits) ---
    trend_dir = None
    if date_col is not None:
        col_sql = f"f.{_q(adapter, date_col.name)}"
        expr = _date_bucket(adapter, "month", col_sql)
        metric_expr = f"sum({measure_sql})" if measure_sql else "count(*)"
        sql = (
            f"SELECT {expr} AS periode, {metric_expr} AS valeur "
            f"FROM {adapter.qualified(fact.schema, fact.name)} f "
            f"WHERE {col_sql} IS NOT NULL GROUP BY {expr} ORDER BY {expr}"
        )
        try:
            res = adapter.run_query(sql, connection_id=conn.id, **guard_args)
            rows = [[r[0], _num(r[1])] for r in res.rows]
        except Exception as exc:  # noqa: BLE001
            log.info("Étape tendance ignorée : %s", exc)
            rows = []
        if len(rows) >= 2:
            queries.append(res.guarded_sql)
            inv.trend_columns = ["periode", "valeur"]
            inv.trend_rows = rows
            first, last = rows[0][1], rows[-1][1]
            lo = min(rows, key=lambda r: r[1])
            pct = ((last - first) / first * 100) if first else 0
            trend_dir = "baisse" if pct < -2 else "hausse" if pct > 2 else "stable"
            inv.plan.append({"title": "Tendance dans le temps",
                             "rationale": "Situer l'ampleur et le sens de la variation avant d'en chercher la cause."})
            inv.steps.append(asdict(Step(
                title="Tendance dans le temps",
                question=f"Comment évolue {metric} ?",
                rationale="On mesure d'abord l'ampleur et le point bas.",
                sql=res.guarded_sql,
                finding=(f"{metric} passe de {_fmt(first)} ({rows[0][0]}) à {_fmt(last)} "
                         f"({rows[-1][0]}), soit {pct:+.0f}% — point bas en {lo[0]} "
                         f"({_fmt(lo[1])})."),
                figures=[{"label": "début", "value": round(first)},
                         {"label": "fin", "value": round(last)},
                         {"label": "variation_%", "value": round(pct, 1)}],
            )))

    if date_col is not None and inv.trend_rows:
        inv.journal.append({"t": _now(), "phase": "analysis", "status": "accepted",
                            "detail": f"Tendance temporelle établie ({trend_dir})."})

    # Mémoire du moteur (J) : on teste EN PRIORITÉ les stratégies qui se sont
    # révélées efficaces par le passé pour ce sujet (chaînes de jointures utiles).
    from app.services import reasoning_memory as memory

    dims, prioritized = memory.rank(dims, db, conn.id, fact.name)
    if prioritized:
        inv.journal.append({"t": _now(), "phase": "plan", "status": "info",
                            "detail": "Mémoire du moteur : stratégie(s) priorisée(s) car "
                                      f"efficace(s) par le passé — {', '.join(prioritized)}."})

    # --- Étapes par dimension : plan puis exécution ---
    segmentations = []
    observed: list[tuple[str, float]] = []
    for dim in dims[:_MAX_DIM_STEPS]:
        seg = _run_segmentation(adapter, conn.id, guard_args, fact, dim, measure_sql)
        if seg is not None:
            segmentations.append(seg)
            observed.append((dim.label, seg.power))
            inv.journal.append({"t": _now(), "phase": "analysis", "status": "info",
                                "detail": f"Analyse « {dim.label} » : signal mesuré (force {seg.power:.2f})."})
        else:
            observed.append((dim.label, 0.0))
            inv.journal.append({"t": _now(), "phase": "analysis", "status": "rejected",
                                "detail": f"Analyse « {dim.label} » écartée : aucun signal exploitable."})
    segmentations.sort(key=lambda s: s.power, reverse=True)

    # Apprentissage : on mémorise l'efficacité observée (le caller valide).
    memory.record(db, conn.id, fact.name, observed)

    # --- Test de SAISONNALITÉ (P-07) : la baisse est-elle juste un creux annuel ? -
    # Beaucoup d'analystes comparent au mois précédent (« ça baisse ! ») alors qu'il
    # faut comparer à la MÊME période l'an dernier. Si le niveau récent est conforme
    # (ou supérieur) à l'an dernier, la baisse est SAISONNIÈRE — pas une anomalie.
    if date_col is not None and trend_dir == "baisse" and len(inv.trend_rows) >= 16:
        labels = [str(r[0]) for r in inv.trend_rows]
        vals = {str(r[0]): _num(r[1]) for r in inv.trend_rows}
        ww = max(2, min(_trailing_run(inv.trend_rows, "baisse") or 4, 6))
        recent = labels[-ww:]

        def _year_ago(lbl: str) -> str:
            y, mth = lbl.split("-")
            return f"{int(y) - 1}-{mth}"

        prev = [_year_ago(x) for x in recent]
        if all(p in vals for p in prev):
            rsum = sum(vals[x] for x in recent)
            psum = sum(vals[p] for p in prev)
            yoy = (rsum - psum) / psum * 100 if psum else 0.0
            if yoy >= -4:   # pas pire qu'à la même période l'an dernier → saisonnier
                inv.seasonal = True
                inv.seasonal_detail = (
                    f"À la même période l'an dernier, {metric} était comparable "
                    f"({yoy:+.0f}% en glissement annuel). La baisse des {ww} derniers "
                    "mois est SAISONNIÈRE (ce creux revient chaque année) — pas une anomalie.")
                inv.plan.append({"title": "Test de saisonnalité",
                                 "rationale": "Comparer à la même période l'an dernier, pas au mois précédent."})
                inv.steps.append(asdict(Step(
                    title="Test de saisonnalité",
                    question=f"La baisse de {metric} est-elle saisonnière ?",
                    rationale="On compare la fenêtre récente à la MÊME période l'an dernier "
                              "(glissement annuel) plutôt qu'à la période précédente.",
                    sql="-- comparaison en glissement annuel (mêmes mois, année N-1) --",
                    finding=inv.seasonal_detail,
                    figures=[{"label": "récent", "value": round(rsum)},
                             {"label": "an dernier", "value": round(psum)},
                             {"label": "glissement_annuel_%", "value": round(yoy, 1)}],
                )))
                inv.journal.append({"t": _now(), "phase": "analysis", "status": "accepted",
                                    "detail": f"Baisse SAISONNIÈRE : {yoy:+.0f}% en glissement annuel "
                                              "(pas d'anomalie)."})

    # --- Attribution de la variation (d'où vient la baisse/hausse ?) ---------
    # Un analyste senior ne dit pas « la majorité du CA vient du plus gros
    # segment » (tautologie) : il dit « la baisse est portée par tel segment ».
    # Sautée si la baisse est purement saisonnière (il n'y a pas d'anomalie à isoler).
    attribution_ranked: list[dict] = []
    if not inv.seasonal and date_col is not None and trend_dir in ("baisse", "hausse") \
            and len(inv.trend_rows) >= 4:
        w = _trailing_run(inv.trend_rows, trend_dir) or 4
        w = max(2, min(w, len(inv.trend_rows) // 2))
        labels = [str(r[0]) for r in inv.trend_rows]
        attribution = _attribute_variation(
            adapter, conn.id, guard_args, fact, dims, measure_sql, date_col,
            labels[-w:], labels[-2 * w:-w], trend_dir,
        )
        sens = "baisse" if trend_dir == "baisse" else "hausse"
        if attribution is not None and attribution["mode"] == "single":
            attribution_ranked = attribution["ranked"]
            inv.attribution = a = attribution["best"]
            # VÉRIFICATION AUTOMATIQUE : ce qui a été testé, chiffré et auditable —
            # remplace le journal introspectif « à première vue… mais en isolant… ».
            _sens_noun = "recul" if trend_dir == "baisse" else "progression"

            def _is_temporal(lbl: str) -> bool:
                l = (lbl or "").lower()
                return any(w in l for w in (
                    "date", "mois", "month", "jour", "day", "année", "annee",
                    "year", "semaine", "week", "trimestre", "quarter"))

            # Axes de comparaison présentables : on écarte le temporel (une date
            # n'est pas une cause métier), on dédoublonne par axe, on ignore le
            # bruit (< 12 %) et on cap à quelques pistes fortes.
            _seen: set[str] = set()
            _tested: list[dict] = []
            for t in attribution.get("tested") or []:
                d = t["dimension"]
                if _is_temporal(d) or d in _seen:
                    continue
                if t["pct"] < 12 and d != a["dimension"]:
                    continue
                _seen.add(d)
                _tested.append(t)
            _tested = _tested[:4]
            if not any(t["dimension"] == a["dimension"] for t in _tested):
                _tested.insert(0, {"dimension": a["dimension"], "segment": a["segment"],
                                   "pct": round(a["contribution_pct"])})

            _init_lbl = initial.label if initial else None
            _init_row = next((t for t in _tested if t["dimension"] == _init_lbl), None)
            if _init_row and _init_lbl and _init_lbl != a["dimension"]:
                _verif_text = (
                    f"Le découpage par « {_init_lbl} » a d'abord été testé ; il explique "
                    f"moins la variation que « {a['dimension']} ». Après comparaison des "
                    f"facteurs, « {a['segment']} » concentre {a['contribution_pct']:.0f}% "
                    f"du {_sens_noun} observé.")
            else:
                _verif_text = (
                    f"Plusieurs axes ont été comparés. « {a['segment']} » concentre "
                    f"{a['contribution_pct']:.0f}% du {_sens_noun} observé — c'est la "
                    f"piste la plus explicative.")
            inv.verification = {
                "text": _verif_text,
                "winner": {"dimension": a["dimension"], "segment": a["segment"],
                           "pct": round(a["contribution_pct"])},
                "tested": _tested,
            }
            finding = (f"Sur les {w} derniers mois, « {a['segment']} » "
                       f"({a['dimension']}) porte {a['contribution_pct']:.0f}% "
                       f"de la {sens} : {metric} y passe de {_fmt(a['prior'])} à "
                       f"{_fmt(a['recent'])}.")
            inv.plan.append({"title": "Attribution de la variation",
                             "rationale": "Isoler d'où vient le changement, pas seulement d'où vient le total."})
            inv.steps.append(asdict(Step(
                title="Attribution de la variation",
                question=f"D'où vient la {sens} de {metric} ?",
                rationale="On compare la fenêtre récente à la précédente, axe par axe, "
                          "pour isoler le segment qui porte réellement le changement.",
                sql=a["sql"], finding=finding,
                figures=[{"label": "avant", "value": round(a["prior"])},
                         {"label": "récent", "value": round(a["recent"])},
                         {"label": "contribution_%", "value": a["contribution_pct"]}],
            )))
            queries.append(a["sql"])
            inv.journal.append({"t": _now(), "phase": "analysis", "status": "accepted",
                                "detail": f"Attribution : « {a['segment']} » ({a['dimension']}) porte "
                                          f"{a['contribution_pct']:.0f}% de la {sens}."})
        elif attribution is not None and attribution["mode"] == "multi":
            # CAUSES MULTIPLES : plusieurs foyers concentrés se partagent la variation.
            inv.multi_causes = attribution["causes"]
            parts = " ; ".join(f"« {c['segment']} » {c['contribution_pct']:.0f}%"
                               for c in attribution["causes"])
            finding = (f"Pas de cause unique : {len(attribution['causes'])} foyers se "
                       f"partagent la {sens} — {parts} (soit {attribution['explained']:.0f}% "
                       f"à eux seuls). Il faut agir sur les trois, pas sur un seul.")
            inv.plan.append({"title": "Attribution de la variation",
                             "rationale": "Repérer les foyers qui se partagent le changement."})
            inv.steps.append(asdict(Step(
                title="Attribution de la variation (causes multiples)",
                question=f"D'où vient la {sens} de {metric} ?",
                rationale="On compare récent vs précédent, axe par axe : ici plusieurs "
                          "segments portent chacun une part notable du changement.",
                sql=attribution["causes"][0]["sql"], finding=finding,
                figures=[{"label": c["segment"], "value": c["contribution_pct"]}
                         for c in attribution["causes"]],
            )))
            queries.append(attribution["causes"][0]["sql"])
            inv.journal.append({"t": _now(), "phase": "analysis", "status": "accepted",
                                "detail": f"Causes multiples ({len(attribution['causes'])}) : {parts}."})
        else:
            # Tendance nette mais aucun segment disproportionné → GÉNÉRALISÉE.
            inv.broad_based = True
            sens = "baisse" if trend_dir == "baisse" else "hausse"
            inv.plan.append({"title": "Attribution de la variation",
                             "rationale": "Chercher un segment qui porte le changement — s'il existe."})
            inv.steps.append(asdict(Step(
                title="Attribution de la variation",
                question=f"D'où vient la {sens} de {metric} ?",
                rationale="On compare la fenêtre récente à la précédente, axe par axe.",
                sql="-- aucun segment disproportionné (lift ≈ 1 partout) --",
                finding=(f"Aucun segment ne se détache : la {sens} est GÉNÉRALISÉE. "
                         "Chaque axe recule à peu près en proportion de sa taille — la "
                         "cause est probablement transverse (prix, saison, effet macro), "
                         "pas un magasin ni une région en particulier."),
                figures=[],
            )))
            inv.journal.append({"t": _now(), "phase": "analysis", "status": "accepted",
                                "detail": f"Aucune cause localisée : {sens} généralisée (lift ≈ 1)."})

    # Ce que disent réellement les données : le facteur dominant.
    if segmentations:
        winner = segmentations[0].dim
        inv.journal.append({"t": _now(), "phase": "analysis", "status": "accepted",
                            "detail": f"Facteur dominant retenu : « {winner.label} »."})
        # Auto-révision : le moteur change d'avis si les données contredisent
        # l'hypothèse de départ. Quand l'attribution existe, elle prime — la
        # cause du CHANGEMENT l'emporte sur la structure du total.
        # Révisions FACTUELLES (pour les rapports/historique) : un constat de
        # comparaison, jamais un « à première vue… mais en isolant… » introspectif.
        # L'UI, elle, s'appuie sur inv.verification (Vérification automatique).
        if inv.attribution is not None and inv.attribution["dimension"] != getattr(initial, "label", None):
            a = inv.attribution
            sens_word = "baisse" if trend_dir == "baisse" else "hausse"
            init_lbl = initial.label if initial else winner.label
            revision = (f"Le découpage par « {init_lbl} » explique moins la variation "
                        f"que « {a['dimension']} » : « {a['segment']} » y concentre "
                        f"{a['contribution_pct']:.0f}% de la {sens_word}.")
            inv.revisions.append(revision)
            inv.journal.append({"t": _now(), "phase": "revision", "status": "info",
                                "detail": revision})
        elif (inv.attribution is None and not inv.broad_based
              and initial is not None and initial.label != winner.label):
            revision = (f"Le découpage par « {initial.label} » explique moins la structure "
                        f"{noun} que « {winner.label} », retenu comme facteur dominant.")
            inv.revisions.append(revision)
            inv.journal.append({"t": _now(), "phase": "revision", "status": "info",
                                "detail": revision})

    for seg in segmentations:
        top = seg.groups[0]
        total = sum((g.total if seg.metric_is_measure else g.n) or 0 for g in seg.groups)
        share = (((top.total if seg.metric_is_measure else top.n) or 0) / total * 100) if total else 0
        inv.plan.append({"title": seg.dim.label, "rationale": _dim_rationale(seg.dim.label)})
        # Constat : gradient (mesure moyenne) ou concentration.
        gradient = None
        if seg.metric_is_measure:
            valued = [g for g in seg.groups if g.avg is not None]
            if len(valued) >= 3:
                hi = max(valued, key=lambda g: g.avg)
                loo = min(valued, key=lambda g: g.avg)
                if loo.avg and hi.avg / loo.avg >= 1.2:
                    gradient = (loo, hi, hi.avg / loo.avg)
        if gradient is not None:
            loo, hi, ratio = gradient
            finding = (f"« {seg.dim.label} » pèse fort : de {_fmt(loo.avg)} ({loo.label}) à "
                       f"{_fmt(hi.avg)} ({hi.label}), soit ×{ratio:.1f}.")
        else:
            finding = (f"Le segment « {top.label} » concentre {share:.0f}% {noun}.")
        inv.steps.append(asdict(Step(
            title=seg.dim.label,
            question=f"Comment se répartit {metric} par « {seg.dim.label} » ?",
            rationale=_dim_rationale(seg.dim.label),
            sql=seg.sql,
            finding=finding,
            figures=[{"label": g.label, "value": round((g.total if seg.metric_is_measure else g.n) or 0)}
                     for g in seg.groups[:4]],
        )))
        queries.append(seg.sql)

    if not inv.steps:
        return None

    # --- Synthèse ---
    # L'attribution de la variation prime : c'est la cause du CHANGEMENT (« d'où
    # vient la baisse ? »), pas la structure du total. Elle guide le Decision Engine.
    seen_dims: set[str] = set()
    # Causes MULTIPLES : chaque foyer devient un facteur (même dimension, segments
    # différents) → le Decision Engine peut recommander une action par foyer.
    if inv.multi_causes:
        for c in inv.multi_causes:
            inv.key_drivers.append(
                f"{c['dimension']} — « {c['segment']} » ({c['contribution_pct']:.0f}% de la variation)")
            inv.drivers_struct.append({
                "dimension": c["dimension"], "segment": c["segment"],
                "share": c["contribution_pct"], "samples": c.get("samples", []),
            })
        seen_dims.add(inv.multi_causes[0]["dimension"])

    # Priorité aux facteurs de VARIATION (contribution à la baisse), pas de total.
    # Le premier est la cause dominante ; on n'ajoute un facteur secondaire que
    # s'il est lui aussi nettement concentré (≥ 65 %) — sinon c'est du bruit
    # (un même effet vu sous un autre angle, proche de 50/50).
    for i, a in enumerate(attribution_ranked[:3]):
        if i > 0 and a["contribution_pct"] < 65:
            continue
        inv.key_drivers.append(
            f"{a['dimension']} — « {a['segment']} » ({a['contribution_pct']:.0f}% de la variation)")
        inv.drivers_struct.append({
            "dimension": a["dimension"], "segment": a["segment"],
            "share": a["contribution_pct"], "samples": a.get("samples", []),
        })
        seen_dims.add(a["dimension"])

    # Sans attribution de variation exploitable, on se rabat sur la structure du
    # total — MAIS PAS si la variation est généralisée/saisonnière : émettre un
    # « plus gros segment » y serait une tautologie trompeuse (c'est justement le piège).
    _fallback = segmentations[:3] if (
        not inv.drivers_struct and not inv.broad_based and not inv.seasonal) else []
    for seg in _fallback:
        if seg.dim.label in seen_dims:
            continue
        top = seg.groups[0]
        total = sum((g.total if seg.metric_is_measure else g.n) or 0 for g in seg.groups)
        share = (((top.total if seg.metric_is_measure else top.n) or 0) / total * 100) if total else 0
        inv.key_drivers.append(f"{seg.dim.label} — « {top.label} » ({share:.0f}%)")
        inv.drivers_struct.append({
            "dimension": seg.dim.label, "segment": top.label, "share": round(share, 1),
        })

    parts = []
    if trend_dir == "baisse":
        parts.append(f"{metric} est orienté à la baisse")
    elif trend_dir == "hausse":
        parts.append(f"{metric} est orienté à la hausse")
    elif trend_dir == "stable":
        parts.append(f"{metric} est globalement stable")
    sens = "baisse" if trend_dir == "baisse" else "hausse"
    if inv.seasonal:
        parts = [f"la baisse récente de {metric} est SAISONNIÈRE",
                 inv.seasonal_detail.rstrip(".") if inv.seasonal_detail else
                 "conforme à la même période l'an dernier"]
    elif inv.attribution is not None:
        a = inv.attribution
        parts.append(
            f"la {sens} est portée à {a['contribution_pct']:.0f}% par « {a['segment']} » "
            f"({a['dimension']})"
        )
    elif inv.multi_causes:
        foyers = ", ".join(f"« {c['segment']} » ({c['contribution_pct']:.0f}%)"
                           for c in inv.multi_causes)
        parts.append(
            f"la {sens} ne vient pas d'une cause unique mais de "
            f"{len(inv.multi_causes)} foyers — {foyers}"
        )
    elif inv.broad_based:
        parts.append(
            f"la {sens} est GÉNÉRALISÉE : aucun segment ne se détache "
            "(cause probablement transverse — prix, saison, effet macro)"
        )
    elif segmentations:
        d0 = segmentations[0]
        parts.append(
            f"la variation est surtout structurée par « {d0.dim.label} » "
            f"(segment dominant « {d0.groups[0].label} »)"
        )
    inv.conclusion = ("Conclusion : " + " ; ".join(parts) + ".") if parts else \
        "Conclusion : facteurs répartis, pas de cause unique dominante."

    if inv.seasonal:
        inv.recommendations.append(
            "Pas d'action corrective : la baisse est saisonnière. Suivre l'indicateur "
            "en GLISSEMENT ANNUEL (même mois l'an dernier), pas d'un mois sur l'autre, "
            "et vérifier que la reprise post-creux a bien lieu comme les années passées."
        )
    elif inv.attribution is not None:
        a = inv.attribution
        inv.recommendations.append(
            f"Concentrer l'action sur « {a['segment']} » ({a['dimension']}) — "
            f"qui porte l'essentiel de la variation — et suivre son redressement."
        )
    elif inv.multi_causes:
        foyers = ", ".join(f"« {c['segment']} »" for c in inv.multi_causes)
        inv.recommendations.append(
            f"Agir sur les {len(inv.multi_causes)} foyers à la fois ({foyers}) : "
            "un plan pour un seul ne redressera qu'une fraction de la variation."
        )
    elif inv.broad_based:
        inv.recommendations.append(
            "Chercher une cause TRANSVERSE (politique de prix, saisonnalité, "
            "contexte macro) plutôt qu'un magasin ou un segment : la baisse est diffuse."
        )
    elif segmentations:
        d0 = segmentations[0]
        inv.recommendations.append(
            f"Concentrer l'action sur « {d0.groups[0].label} » ({d0.dim.label}) et suivre son évolution."
        )
    if trend_dir == "baisse" and inv.trend_rows and not inv.seasonal:
        lo = min(inv.trend_rows, key=lambda r: r[1])
        inv.recommendations.append(
            f"Investiguer la période « {lo[0]} » (point bas) : événement métier, promotion, ou données incomplètes ?"
        )
    inv.recommendations.append(
        "Valider ces pistes avec le métier avant décision (l'agent identifie des corrélations, pas des causes certaines)."
    )

    inv.journal.append({"t": _now(), "phase": "synthesis", "status": "accepted",
                        "detail": "Synthèse : facteurs classés, conclusion et recommandations produites."})

    inv.queries = queries
    return inv


def summary_message(inv: Investigation) -> str:
    lead = f"J'ai mené une investigation en {len(inv.steps)} étape(s) sur « {inv.subject} »."
    return f"{lead} {inv.conclusion}"

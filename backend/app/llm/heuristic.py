"""Fournisseur LLM heuristique — fonctionne HORS-LIGNE, sans clé API.

Ce n'est pas un vrai modèle de langage : c'est un moteur de règles qui couvre
un sous-ensemble de questions fréquentes (comptage, liste, agrégats simples,
top N). Il permet de faire tourner et tester Noreon de bout en bout sans
dépendance externe. Dès qu'une clé (OpenAI / Anthropic / Mistral) est
configurée pour le tenant, la factory bascule sur le vrai fournisseur et la
compréhension du langage naturel devient complète.

Conformément au principe « il ne devine jamais silencieusement » (Module 7),
lorsqu'il ne sait pas résoudre une question il renvoie `clarification_needed`
plutôt que de produire un SQL au hasard.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.llm.base import (
    AnalysisResult,
    LLMMessage,
    LLMProvider,
    SQLGenerationResult,
)


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def _norm(text: str) -> str:
    return _strip_accents(text.lower())


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", _norm(text))


# Synonymes métier FR/EN → aident l'appariement question ↔ table/colonne.
_SYNONYMS = {
    "client": ["customer", "customers", "clients", "client", "compte", "account"],
    "clients": ["customer", "customers", "clients"],
    "commande": ["order", "orders", "commande", "commandes", "vente", "ventes", "sale", "sales"],
    "commandes": ["order", "orders", "commandes", "ventes", "sales"],
    "vente": ["sale", "sales", "order", "orders", "vente", "ventes"],
    "ventes": ["sale", "sales", "orders", "ventes"],
    "produit": ["product", "products", "produit", "produits", "article", "articles"],
    "produits": ["product", "products", "produits", "articles"],
    "magasin": ["store", "stores", "shop", "magasin", "magasins", "boutique"],
    "magasins": ["store", "stores", "magasins"],
    "paiement": ["payment", "payments", "paiement", "paiements"],
    "paiements": ["payment", "payments", "paiements"],
    "montant": ["amount", "price", "total", "net_price", "montant", "prix"],
    "chiffre": ["amount", "revenue", "total", "ca"],
}


@dataclass
class _Column:
    name: str
    dtype: str
    is_pk: bool = False


@dataclass
class _Table:
    schema: str
    name: str
    columns: list[_Column]
    rows: int | None = None

    @property
    def fq(self) -> str:
        return f"{self.schema}.{self.name}"


def parse_schema_context(schema_context: str) -> tuple[list[_Table], dict[str, set[str]]]:
    """Parse le contexte de schéma textuel produit par le service chat.

    Format attendu (aussi lisible par un vrai LLM) :

        Table public.customers (rows~39000)
          - id integer PK
          - email varchar

        Dictionnaire métier validé :
          Concept Client = customers.id, customers.full_name

    Renvoie (tables, synonymes métier {nom_table: {termes}}), le dictionnaire
    validé servant de mémoire entreprise à l'appariement.
    """
    tables: list[_Table] = []
    synonyms: dict[str, set[str]] = {}
    current: _Table | None = None
    for line in schema_context.splitlines():
        m = re.match(r"^Table\s+([\w]+)\.([\w]+)(?:\s*\(rows~?(\d+)\))?", line.strip())
        if m:
            current = _Table(
                schema=m.group(1),
                name=m.group(2),
                columns=[],
                rows=int(m.group(3)) if m.group(3) else None,
            )
            tables.append(current)
            continue
        cm = re.match(r"^-\s+([\w]+)\s+([\w()]+)(\s+PK)?", line.strip())
        if cm and current is not None:
            current.columns.append(
                _Column(name=cm.group(1), dtype=cm.group(2), is_pk=bool(cm.group(3)))
            )
            continue
        # Dictionnaire métier validé : « Concept Client = customers.id, orders.customer_id »
        km = re.match(r"^Concept\s+(.+?)\s*=\s*(.+)$", line.strip())
        if km:
            concept = _norm(km.group(1)).strip()
            for ref in km.group(2).split(","):
                ref = ref.strip()
                if "." in ref:
                    tname = ref.split(".")[0].strip()
                    synonyms.setdefault(tname, set()).add(concept)
    return tables, synonyms


@dataclass
class _Definition:
    name: str          # nom normalisé (accents/casse)
    raw_name: str      # nom d'origine
    kind: str          # measure | segment
    table: str         # nom court de la table
    fq: str            # schema.table
    expression: str | None
    filter_sql: str | None


def parse_definitions(schema_context: str) -> list[_Definition]:
    """Extrait les définitions métier du contexte (voir definitions_context)."""
    defs: list[_Definition] = []
    for line in schema_context.splitlines():
        s = line.strip()
        m = re.match(r"^Mesure\s+(.+?)\s*=\s*(.+?)\s+sur\s+([\w]+)\.([\w]+)(?:\s+filtre:\s*(.+))?$", s)
        if m:
            defs.append(_Definition(
                name=_norm(m.group(1)).strip(), raw_name=m.group(1).strip(), kind="measure",
                table=m.group(4), fq=f"{m.group(3)}.{m.group(4)}",
                expression=m.group(2).strip(), filter_sql=(m.group(5) or "").strip() or None,
            ))
            continue
        sm = re.match(r"^Segment\s+(.+?)\s+sur\s+([\w]+)\.([\w]+)\s+filtre:\s*(.+)$", s)
        if sm:
            defs.append(_Definition(
                name=_norm(sm.group(1)).strip(), raw_name=sm.group(1).strip(), kind="segment",
                table=sm.group(3), fq=f"{sm.group(2)}.{sm.group(3)}",
                expression=None, filter_sql=sm.group(4).strip(),
            ))
    return defs


class HeuristicProvider(LLMProvider):
    name = "heuristic"
    dialect = "postgres"

    # ---- appariement -----------------------------------------------------
    def _score_table(
        self, table: _Table, q_tokens: set[str], biz_syns: dict[str, set[str]] | None = None
    ) -> float:
        score = 0.0
        name_variants = {table.name, table.name.rstrip("s"), table.name + "s"}
        table_biz = (biz_syns or {}).get(table.name, set())
        for tok in q_tokens:
            variants = set(_SYNONYMS.get(tok, [])) | {tok, tok.rstrip("s"), tok + "s"}
            if variants & table_biz:
                # Dictionnaire métier validé par l'humain : signal le plus fort.
                score += 3.0
            elif variants & name_variants:
                score += 2.0
            elif tok in table.name or table.name in tok:
                score += 1.0
        return score

    def _pick_table(
        self, tables: list[_Table], q_tokens: set[str], biz_syns: dict[str, set[str]] | None = None
    ) -> _Table | None:
        if not tables:
            return None
        scored = sorted(
            tables, key=lambda t: self._score_table(t, q_tokens, biz_syns), reverse=True
        )
        best = scored[0]
        # Seuil : on exige une vraie correspondance (synonyme métier ou nom
        # exact/pluriel), pas une simple coïncidence de sous-chaîne, sinon on
        # demande une clarification plutôt que de deviner.
        if self._score_table(best, q_tokens, biz_syns) < 2.0:
            return None
        return best

    # Marqueurs d'un filtre/qualificatif dans la question (« clients QUI SONT
    # heureux », « commandes AYANT … »). Ce qui suit doit correspondre à une
    # colonne connue ; sinon l'information est absente des données → refus.
    _FILTER_MARKERS = r"\b(qui sont|qui ont|sont|est|ayant|dont|etant)\b"
    _PREDICATE_STOP = {
        "combien", "nombre", "count", "compter", "quel", "quelle", "quels", "quelles",
        "de", "des", "du", "la", "le", "les", "un", "une", "au", "aux", "en",
        "sont", "est", "qui", "ont", "ayant", "dont", "avec", "par", "et", "ou",
        "moyenne", "moyen", "moyens", "total", "totale", "somme", "montant",
        "montre", "liste", "afficher", "affiche", "donne", "donner",
        "how", "many", "the", "of", "are", "is", "with", "that", "has", "have",
    }

    def _known_terms(self, table: _Table, biz_syns: dict[str, set[str]] | None) -> set[str]:
        terms: set[str] = {_norm(table.name)}
        for c in table.columns:
            terms.add(c.name.lower())
            terms.update(_tokens(c.name))
        for syn in (biz_syns or {}).get(table.name, set()):
            terms.update(_tokens(syn))
        return terms

    @staticmethod
    def _term_known(tok: str, known: set[str]) -> bool:
        variants = set(_SYNONYMS.get(tok, [])) | {tok}
        for v in variants:
            if not v:
                continue
            if v in known or any(v in k or k in v for k in known):
                return True
        return False

    def _unresolved_filter(
        self, question: str, table: _Table, biz_syns: dict[str, set[str]] | None
    ) -> list[str] | None:
        """Détecte un prédicat de filtre dont AUCUN terme ne correspond au schéma.

        « Combien de clients sont heureux ? » → « heureux » n'est ni une colonne
        ni une valeur connue : plutôt que de compter tous les clients (deviner en
        ignorant le filtre), le moteur refuse honnêtement.
        """
        q = _norm(question)
        m = re.search(self._FILTER_MARKERS + r"\s+(.+)$", q)
        if not m:
            return None
        tail_tokens = [t for t in _tokens(m.group(2))
                       if t not in self._PREDICATE_STOP and len(t) > 2]
        if not tail_tokens:
            return None
        known = self._known_terms(table, biz_syns)
        unknown = [t for t in tail_tokens if not self._term_known(t, known)]
        # Refus seulement si TOUT le prédicat est étranger au schéma (sinon on
        # laisse le pipeline traiter la partie reconnue).
        return unknown if unknown and len(unknown) == len(tail_tokens) else None

    def _pick_column(
        self,
        table: _Table,
        q_tokens: set[str],
        numeric_only: bool = False,
        exclude: set[str] | None = None,
    ) -> _Column | None:
        candidates = [c for c in table.columns if c.name not in (exclude or set())]
        if numeric_only:
            candidates = [c for c in candidates if _is_numeric(c.dtype)]
        best: _Column | None = None
        best_score = 0.0
        for col in candidates:
            s = 0.0
            for tok in q_tokens:
                variants = set(_SYNONYMS.get(tok, [])) | {tok}
                if any(v and (v == col.name or v in col.name or col.name in v) for v in variants):
                    s += 1.0
            if s > best_score:
                best, best_score = col, s
        # Pas de correspondance explicite : on ne devine pas une colonne au
        # hasard (ex. la clé primaire). Le caller demandera une clarification.
        return best

    _TIME_UNITS = {
        "mois": "month", "month": "month",
        "jour": "day", "day": "day", "jours": "day",
        "semaine": "week", "week": "week",
        "an": "year", "annee": "year", "annees": "year", "year": "year",
        "trimestre": "quarter", "quarter": "quarter",
    }

    def _date_trunc(self, unit: str, col: str) -> str:
        """Troncature de date selon le dialecte du moteur source."""
        if self.dialect == "mysql":
            fmt = {"year": "%Y-01-01", "quarter": "%Y-%m-01", "month": "%Y-%m-01",
                   "week": "%x-%v", "day": "%Y-%m-%d"}.get(unit, "%Y-%m-%d")
            return f"DATE_FORMAT({col}, '{fmt}')"
        if self.dialect == "sqlite":
            fmt = {"year": "%Y-01-01", "month": "%Y-%m-01", "day": "%Y-%m-%d",
                   "week": "%Y-%W"}.get(unit, "%Y-%m-%d")
            return f"strftime('{fmt}', {col})"
        return f"date_trunc('{unit}', {col})::date"  # postgres

    def _pick_group(self, table: _Table, q: str) -> tuple[str, str, bool] | None:
        """Détecte un « par X » → (expression SQL, alias, est_temporel)."""
        m = re.search(r"\b(?:par|by|per)\s+([a-z0-9_]+)", q)
        if not m:
            return None
        token = m.group(1)

        # « par mois/jour/… » → troncature de date (dialecte) sur la 1re colonne temporelle.
        unit = self._TIME_UNITS.get(token)
        if unit:
            date_col = next(
                (c for c in table.columns if any(k in c.dtype.lower() for k in ("date", "timestamp", "time"))),
                None,
            )
            if date_col is not None:
                expr = self._date_trunc(unit, date_col.name)
                return expr, unit, True

        # « par <colonne> » → colonne correspondante de la table.
        variants = set(_SYNONYMS.get(token, [])) | {token, token.rstrip("s"), token + "s"}
        for col in table.columns:
            if col.name in variants or any(v and v in col.name for v in variants):
                return col.name, col.name, False
        return None

    def _mentions(self, name: str, q: str) -> bool:
        """Vrai si tous les mots du nom de définition figurent dans la question
        (tolérance singulier/pluriel), ex. « client fidele » ↔ « clients fideles »."""
        name_toks = _tokens(name)
        if not name_toks:
            return False
        q_toks = set(_tokens(q))
        q_norm = {t.rstrip("s") for t in q_toks}
        for tok in name_toks:
            forms = {tok, tok.rstrip("s"), tok + "s"}
            if not (forms & q_toks) and tok.rstrip("s") not in q_norm:
                return False
        return True

    def _resolve_definition(
        self, definitions: list[_Definition], tables: list[_Table], q: str
    ) -> SQLGenerationResult | None:
        """Résout une question qui mobilise une mesure ou un segment nommé."""
        measures = [d for d in definitions if d.kind == "measure" and self._mentions(d.name, q)]
        segments = [d for d in definitions if d.kind == "segment" and self._mentions(d.name, q)]
        if not measures and not segments:
            return None

        def _alias(name: str) -> str:
            a = re.sub(r"[^a-z0-9]+", "_", _norm(name)).strip("_")
            return a or "valeur"

        # --- Mesure (éventuellement restreinte par un segment de même table) ---
        if measures:
            d = measures[0]
            table_obj = next((t for t in tables if t.name == d.table), None)
            filters = [d.filter_sql] if d.filter_sql else []
            used_segment = None
            for seg in segments:
                if seg.table == d.table and seg.filter_sql:
                    filters.append(f"({seg.filter_sql})")
                    used_segment = seg
            where = f" WHERE {' AND '.join(filters)}" if filters else ""
            alias = _alias(d.raw_name)
            assumptions = [f"Mesure métier « {d.raw_name} » = {d.expression} sur {d.fq}."]
            if used_segment:
                assumptions.append(f"Restreinte au segment « {used_segment.raw_name} ».")

            group = self._pick_group(table_obj, q) if table_obj else None
            if group is not None:
                gexpr, galias, is_time = group
                order = "1" if is_time else "2 DESC"
                sql = (
                    f"SELECT {gexpr} AS {galias}, {d.expression} AS {alias} "
                    f"FROM {d.fq}{where} GROUP BY 1 ORDER BY {order}"
                )
                assumptions.append(f"Ventilé par « {galias} ».")
                cols = [alias, galias]
            else:
                sql = f"SELECT {d.expression} AS {alias} FROM {d.fq}{where}"
                cols = [alias]
            return SQLGenerationResult(
                sql=sql, tables_used=[d.fq], columns_used=cols,
                assumptions=assumptions,
                rationale=f"Question résolue via la définition métier « {d.raw_name} ».",
            )

        # --- Segment seul : comptage ou liste de la population définie ---
        d = segments[0]
        where = f" WHERE {d.filter_sql}"
        assumptions = [f"Segment métier « {d.raw_name} » sur {d.fq} : {d.filter_sql}."]
        if re.search(r"\b(combien|nombre|count|compter|how many)\b", q):
            sql = f"SELECT count(*) AS total FROM {d.fq}{where}"
            return SQLGenerationResult(
                sql=sql, tables_used=[d.fq], columns_used=[],
                assumptions=assumptions,
                rationale=f"Comptage du segment métier « {d.raw_name} ».",
            )
        table_obj = next((t for t in tables if t.name == d.table), None)
        cols = _select_columns(table_obj) if table_obj else "*"
        sql = f"SELECT {cols} FROM {d.fq}{where} LIMIT 100"
        assumptions.append("Aperçu limité à 100 lignes.")
        return SQLGenerationResult(
            sql=sql, tables_used=[d.fq],
            columns_used=[c.name for c in table_obj.columns[:12]] if table_obj else [],
            assumptions=assumptions,
            rationale=f"Liste du segment métier « {d.raw_name} ».",
        )

    # ---- interface -------------------------------------------------------
    def generate_sql(
        self,
        question: str,
        schema_context: str,
        dialect: str = "postgres",
        history: list[LLMMessage] | None = None,
    ) -> SQLGenerationResult:
        self.dialect = dialect  # oriente la troncature de date (_date_trunc)
        tables, biz_syns = parse_schema_context(schema_context)
        definitions = parse_definitions(schema_context)
        q = _norm(question)
        q_tokens = set(_tokens(question))

        # Définitions métier réutilisables (V0.4) : prioritaires — une mesure
        # ou un segment nommé fait foi sur l'interprétation générique.
        resolved = self._resolve_definition(definitions, tables, q)
        if resolved is not None:
            return resolved

        table = self._pick_table(tables, q_tokens, biz_syns)
        if table is None:
            return SQLGenerationResult(
                sql="",
                clarification_needed=(
                    "Je n'ai pas identifié la table concernée par votre question. "
                    "Pouvez-vous préciser sur quelles données porter l'analyse "
                    f"(tables disponibles : {', '.join(t.name for t in tables) or 'aucune'}) ?"
                ),
                rationale="Aucune table du schéma ne correspond aux termes de la question.",
            )

        # Refus honnête : la question porte un filtre sur une information absente
        # des données (ex. « clients heureux ») → ne jamais compter en ignorant
        # le filtre.
        unknown = self._unresolved_filter(question, table, biz_syns)
        if unknown:
            return SQLGenerationResult(
                sql="",
                unanswerable=(
                    "Impossible de répondre avec les données disponibles : "
                    f"« {' '.join(unknown)} » ne correspond à aucune colonne connue "
                    f"de « {table.name} ». Aucune donnée ne permet ce filtre."
                ),
                rationale=f"Filtre non résoluble sur {table.name} : {', '.join(unknown)}.",
            )

        assumptions: list[str] = []
        group = self._pick_group(table, q)

        # --- agrégats : moyenne / somme ---
        agg = None
        if re.search(r"\b(moyenne|average|avg|moyen)\b", q):
            agg = "avg"
        elif re.search(r"\b(somme|total|sum|chiffre d.?affaires|ca)\b", q):
            agg = "sum"

        if agg:
            # La colonne de regroupement (et les clés techniques) ne sont pas
            # des candidates à l'agrégat : « total par magasin » agrège le
            # montant, pas store_id.
            excluded = {group[1]} if group else set()
            if group and not group[2]:
                excluded.add(group[0])
            col = self._pick_column(table, q_tokens, numeric_only=True, exclude=excluded)
            if col is None:
                # Hypothèse explicite (jamais silencieuse) : s'il n'existe
                # qu'UNE colonne numérique métier (hors clés techniques),
                # on la retient en le signalant dans les hypothèses.
                business_numeric = [
                    c for c in table.columns
                    if _is_numeric(c.dtype) and not c.is_pk
                    and not c.name.lower().endswith("id") and c.name not in excluded
                ]
                if len(business_numeric) == 1:
                    col = business_numeric[0]
                    assumptions.append(
                        f"Aucune colonne nommée dans la question : « {col.name} » retenue "
                        f"(seule mesure numérique de {table.name})."
                    )
                else:
                    return SQLGenerationResult(
                        sql="",
                        clarification_needed="Sur quelle colonne numérique dois-je calculer cet agrégat ?",
                    )
            fn = "avg" if agg == "avg" else "sum"
            if group is not None:
                gexpr, galias, is_time = group
                order = "1" if is_time else "2 DESC"
                sql = (
                    f"SELECT {gexpr} AS {galias}, {fn}({col.name}) AS {fn}_{col.name} "
                    f"FROM {table.fq} GROUP BY 1 ORDER BY {order}"
                )
                assumptions.append(
                    f"Agrégat {fn} sur « {col.name} », regroupé par « {galias} »."
                )
                return SQLGenerationResult(
                    sql=sql,
                    tables_used=[table.fq],
                    columns_used=[col.name, galias],
                    assumptions=assumptions,
                    rationale=f"Calcul de {fn} sur {table.name}, ventilé par {galias}.",
                )
            sql = f"SELECT {fn}({col.name}) AS {fn}_{col.name} FROM {table.fq}"
            assumptions.append(f"Agrégat {fn} appliqué sur la colonne « {col.name} ».")
            return SQLGenerationResult(
                sql=sql,
                tables_used=[table.fq],
                columns_used=[col.name],
                assumptions=assumptions,
                rationale=f"Question interprétée comme un calcul de {fn} sur {table.name}.",
            )

        # --- comptage ---
        if re.search(r"\b(combien|nombre|count|compter|how many)\b", q):
            if group is not None:
                gexpr, galias, is_time = group
                order = "1" if is_time else "2 DESC"
                sql = (
                    f"SELECT {gexpr} AS {galias}, count(*) AS total "
                    f"FROM {table.fq} GROUP BY 1 ORDER BY {order}"
                )
                assumptions.append(f"Comptage regroupé par « {galias} ».")
                return SQLGenerationResult(
                    sql=sql,
                    tables_used=[table.fq],
                    columns_used=[galias],
                    assumptions=assumptions,
                    rationale=f"Comptage des lignes de {table.name}, ventilé par {galias}.",
                )
            sql = f"SELECT count(*) AS total FROM {table.fq}"
            return SQLGenerationResult(
                sql=sql,
                tables_used=[table.fq],
                columns_used=[],
                rationale=f"Question interprétée comme un comptage de lignes de {table.name}.",
            )

        # --- top N par colonne ---
        m = re.search(r"\b(top|meilleurs?|plus (?:grands?|gros|eleves?)|highest|top)\b.*?(\d+)?", q)
        limit_m = re.search(r"\b(\d+)\b", q)
        if re.search(r"\btop\b|\bmeilleur|plus (grand|gros|eleve)|highest", q):
            order_col = self._pick_column(table, q_tokens, numeric_only=True)
            n = int(limit_m.group(1)) if limit_m else 10
            if order_col is not None:
                cols = _select_columns(table)
                sql = (
                    f"SELECT {cols} FROM {table.fq} "
                    f"ORDER BY {order_col.name} DESC NULLS LAST LIMIT {n}"
                )
                assumptions.append(f"Classement décroissant sur « {order_col.name} », {n} lignes.")
                return SQLGenerationResult(
                    sql=sql,
                    tables_used=[table.fq],
                    columns_used=[order_col.name],
                    assumptions=assumptions,
                    rationale=f"Top {n} de {table.name} par {order_col.name}.",
                )

        # --- liste / affichage par défaut ---
        n = int(limit_m.group(1)) if limit_m else 100
        cols = _select_columns(table)
        sql = f"SELECT {cols} FROM {table.fq} LIMIT {n}"
        assumptions.append(f"Aperçu limité à {n} lignes (aucun filtre explicite détecté).")
        return SQLGenerationResult(
            sql=sql,
            tables_used=[table.fq],
            columns_used=[c.name for c in table.columns[:12]],
            assumptions=assumptions,
            rationale=f"Question interprétée comme un aperçu de {table.name}.",
        )

    def analyze_results(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[list],
    ) -> AnalysisResult:
        # Rapport chiffré calculé hors-ligne (Module 10) : tendances,
        # anomalies, concentration — voir app/services/analyst.py.
        from app.services.analyst import analyze

        return analyze(question, columns, rows)


def _is_numeric(dtype: str) -> bool:
    d = dtype.lower()
    return any(k in d for k in ("int", "numeric", "decimal", "real", "double", "float", "money"))


def _select_columns(table: _Table, max_cols: int = 12) -> str:
    if not table.columns:
        return "*"
    names = [c.name for c in table.columns[:max_cols]]
    return ", ".join(names)

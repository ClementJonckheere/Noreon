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


def parse_schema_context(schema_context: str) -> list[_Table]:
    """Parse le contexte de schéma textuel produit par le service chat.

    Format attendu (aussi lisible par un vrai LLM) :

        Table public.customers (rows~39000)
          - id integer PK
          - email varchar
    """
    tables: list[_Table] = []
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
    return tables


class HeuristicProvider(LLMProvider):
    name = "heuristic"

    # ---- appariement -----------------------------------------------------
    def _score_table(self, table: _Table, q_tokens: set[str]) -> float:
        score = 0.0
        name_variants = {table.name, table.name.rstrip("s"), table.name + "s"}
        for tok in q_tokens:
            variants = set(_SYNONYMS.get(tok, [])) | {tok, tok.rstrip("s"), tok + "s"}
            if variants & name_variants:
                score += 2.0
            elif tok in table.name or table.name in tok:
                score += 1.0
        return score

    def _pick_table(self, tables: list[_Table], q_tokens: set[str]) -> _Table | None:
        if not tables:
            return None
        scored = sorted(tables, key=lambda t: self._score_table(t, q_tokens), reverse=True)
        best = scored[0]
        # Seuil : on exige une vraie correspondance (synonyme métier ou nom
        # exact/pluriel), pas une simple coïncidence de sous-chaîne, sinon on
        # demande une clarification plutôt que de deviner.
        if self._score_table(best, q_tokens) < 2.0:
            return None
        return best

    def _pick_column(self, table: _Table, q_tokens: set[str], numeric_only: bool = False) -> _Column | None:
        candidates = table.columns
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

    # ---- interface -------------------------------------------------------
    def generate_sql(
        self,
        question: str,
        schema_context: str,
        dialect: str = "postgres",
        history: list[LLMMessage] | None = None,
    ) -> SQLGenerationResult:
        tables = parse_schema_context(schema_context)
        q = _norm(question)
        q_tokens = set(_tokens(question))

        table = self._pick_table(tables, q_tokens)
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

        assumptions: list[str] = []

        # --- agrégats : moyenne / somme ---
        agg = None
        if re.search(r"\b(moyenne|average|avg|moyen)\b", q):
            agg = "avg"
        elif re.search(r"\b(somme|total|sum|chiffre d.?affaires|ca)\b", q):
            agg = "sum"

        if agg:
            col = self._pick_column(table, q_tokens, numeric_only=True)
            if col is None:
                return SQLGenerationResult(
                    sql="",
                    clarification_needed="Sur quelle colonne numérique dois-je calculer cet agrégat ?",
                )
            fn = "avg" if agg == "avg" else "sum"
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
        n = len(rows)
        if n == 0:
            return AnalysisResult(
                summary="La requête n'a retourné aucune ligne.",
                observations=["Le périmètre filtré est peut-être trop restrictif."],
            )
        obs: list[str] = [f"{n} ligne(s) retournée(s), {len(columns)} colonne(s)."]
        # Petit résumé numérique si une seule cellule numérique (agrégat)
        if n == 1 and len(columns) == 1 and _is_number(rows[0][0]):
            return AnalysisResult(
                summary=f"Résultat : {columns[0]} = {rows[0][0]}.",
                observations=obs,
            )
        return AnalysisResult(
            summary=f"{n} enregistrement(s) correspondant à la question.",
            observations=obs,
            recommendations=[
                "Fournisseur heuristique actif : configurez une clé LLM (OpenAI/Anthropic/Mistral) "
                "pour une interprétation métier complète."
            ],
        )


def _is_numeric(dtype: str) -> bool:
    d = dtype.lower()
    return any(k in d for k in ("int", "numeric", "decimal", "real", "double", "float", "money"))


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _select_columns(table: _Table, max_cols: int = 12) -> str:
    if not table.columns:
        return "*"
    names = [c.name for c in table.columns[:max_cols]]
    return ", ".join(names)

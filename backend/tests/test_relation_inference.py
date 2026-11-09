"""Inférence de relations par RECOUVREMENT DE VALEURS (P-05).

Une FK non déclarée est retrouvée si les valeurs de la colonne sont incluses dans
la clé d'une autre table ET en couvrent une part quasi-totale — sans jamais
confondre un attribut (âge) inclus par hasard dans des identifiants.
"""
from __future__ import annotations

from app.services.sources.base import ColumnInfo, TableInfo, infer_value_overlap


def _col(name, dtype="integer", pk=False):
    return ColumnInfo(name=name, ordinal=0, data_type=dtype, is_nullable=True, default=None, is_pk=pk)


def _tables():
    stores = TableInfo("public", "t_s", "table", 6, None,
                       columns=[_col("k0", pk=True), _col("a3", "varchar")])
    orders = TableInfo("public", "t_o", "table", 8000, None,
                       columns=[_col("k3", pk=True), _col("col_002"),   # → t_s (FK cachée)
                                _col("age")])                            # attribut, PAS une FK
    return [stores, orders]


def test_infers_hidden_fk_by_value_overlap():
    tables = _tables()

    def containment(child, ccol, parent, pk):
        # col_002 : 6 valeurs distinctes, toutes ∈ t_s.k0 (6 clés) → couverture 1.0.
        if ccol.name == "col_002" and parent.name == "t_s":
            return (0, 6, 6)
        # age : 55 valeurs ∈ t_s.k0 ? non (6 clés) → beaucoup d'orphelins.
        if ccol.name == "age" and parent.name == "t_s":
            return (50, 55, 6)
        return None

    rels = infer_value_overlap(tables, related_pairs=set(), containment=containment)
    found = {(r.from_column, r.to_table) for r in rels}
    assert ("col_002", "t_s") in found          # FK cachée retrouvée
    assert all(r.from_column != "age" for r in rels)  # l'âge n'est pas une FK


def test_rejects_attribute_with_partial_coverage():
    """Un attribut (âge 18..72) inclus dans des identifiants (produits 1..80) mais
    n'en couvrant que 69 % n'est PAS une clé étrangère — précision avant rappel."""
    products = TableInfo("public", "t_p", "table", 80, None, columns=[_col("k2", pk=True)])
    customers = TableInfo("public", "t_c", "table", 500, None,
                          columns=[_col("k1", pk=True), _col("age")])

    def containment(child, ccol, parent, pk):
        if ccol.name == "age" and parent.name == "t_p":
            return (0, 55, 80)   # 0 orphelin mais couverture 55/80 = 0.69 < 0.9
        return None

    rels = infer_value_overlap([products, customers], set(), containment)
    assert rels == []


def test_skips_already_related_columns():
    tables = _tables()
    calls = []

    def containment(child, ccol, parent, pk):
        calls.append(ccol.name)
        return (0, 6, 6)

    infer_value_overlap(tables, related_pairs={("public", "t_o", "col_002")},
                        containment=containment)
    assert "col_002" not in calls   # déjà reliée → pas recalculée

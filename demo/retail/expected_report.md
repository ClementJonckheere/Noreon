# Rapport exportable attendu — Retail

Structure du rapport que Noreon doit pouvoir **exporter** (Studio de rapports),
rejouable et sourcé.

## 1. Titre & question
> Diagnostic — Pourquoi le chiffre d'affaires baisse-t-il depuis 4 mois ?

## 2. Synthèse exécutive (3 lignes)
CA −12,8 % depuis février 2025 ; ~ 97 % de la baisse vient de PACA (Marseille +
Nice) ; c'est le panier (−23 %) et non le trafic. Action prioritaire : audit
terrain PACA + réappro High-Tech.

## 3. Chronologie narrée
« Après une stabilité jusqu'à l'automne, le CA recule progressivement pendant
4 périodes consécutives, en s'accélérant. »

## 4. Cause principale (attribution)
Tableau de contribution à la baisse par région (cf. `expected_sql.sql` §2) +
graphique en barres (cf. `expected_charts.md` §2).

## 5. Vérification de la fausse piste
Trafic vs panier PACA + clients actifs stables (§3–4).

## 6. Facteur aggravant
Rupture High-Tech (§5).

## 7. Recommandations par rôle
cf. `expected_decisions.md`.

## 8. Projection d'inaction
« Environ −10 % supplémentaires sur le trimestre si rien ne change (projection,
pas prédiction). »

## 9. Confiance & réserves
Score de confiance + réserves qualité (emails invalides, orphelins) + auto-critique.

## 10. Sources & SQL
Chaque bloc cite ses tables, sa qualité et sa requête (transparence totale).

---
Chaque section doit être **rejouable** (mêmes requêtes, mêmes chiffres) et
**exportable** (le comité repart avec un document, pas une capture d'écran).

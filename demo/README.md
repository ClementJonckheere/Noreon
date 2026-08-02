# Bibliothèque de démonstration Noreon

> Un investisseur, un recruteur, un enseignant ou un client retiendra bien plus
> **une démonstration** qu'une liste de fonctionnalités.

Cette bibliothèque contient des **scénarios métier reproductibles**. Chacun a :

- **une vraie base** (données synthétiques, déterministes, chargées en une commande) ;
- **une vraie histoire** (une cause plantée dans les données — on connaît la réponse) ;
- **une vraie démonstration** (Noreon rejoue le pipeline et on **vérifie** ce qu'il trouve).

## Philosophie : un scénario exceptionnel d'abord

Un scénario irréprochable vaut plus que dix scénarios moyens. On construit donc
dans cet ordre :

1. **Scénario vitrine** — `retail/` *« Pourquoi le CA baisse-t-il depuis 4 mois ? »*
   Poussé au maximum : compréhension → investigation → hypothèses → preuves →
   graphiques → recommandations → projection → Decision Engine → rapport. **✅ livré.**
2. **5 scénarios métier vérifiés** — Retail, CRM, Finance, Supply Chain, RH. *(feuille de route)*
3. **Framework de non-régression** — `Gold Standard → Noreon → écart → score`,
   pour tester chaque évolution du moteur. *(feuille de route)*

| Domaine       | Dossier         | Question                                   | État |
|---------------|-----------------|--------------------------------------------|------|
| Retail        | `retail/`       | Pourquoi le CA baisse-t-il depuis 4 mois ? | ✅ vitrine |
| CRM           | `crm/`          | Pourquoi le churn augmente-t-il ?          | ⏳ à venir |
| Finance       | `finance/`      | Pourquoi la marge diminue-t-elle ?         | ⏳ à venir |
| Supply Chain  | `supply_chain/` | Pourquoi les ruptures augmentent-elles ?   | ⏳ à venir |
| RH            | `hr/`           | Pourquoi les départs augmentent-ils ?      | ⏳ à venir |

## Le Gold Standard : notre meilleur outil de développement

Pour chaque scénario, on écrit **à la main** ce qu'un excellent analyste
produirait — le meilleur rapport possible (`gold_standard.md`). Puis on compare :

```
Gold Standard  →  Noreon  →  Différences  →  Score
```

L'écart n'est pas un échec : c'est la **liste de courses** du développement. Le
scénario vitrine a déjà, à lui seul, révélé un manque majeur du moteur (il
rapportait la *part du total* au lieu de la *contribution à la baisse*) — comblé
par l'**attribution de la variation** (cf. `retail/notes.md` et l'ADR D-30).

## Structure d'un scénario

```
demo/<scenario>/
  README.md              Vue d'ensemble + comparaison Gold ⇄ Noreon
  question.md            La question et son cadrage métier
  gold_standard.md       Le rapport IDÉAL, écrit à la main (référence)
  expected_reasoning.md  Le raisonnement attendu, étape par étape
  expected_sql.sql       Les requêtes clés (auditables)
  expected_charts.md     Les graphiques attendus
  expected_report.md     La structure du rapport exportable
  expected_decisions.md  Les décisions attendues par rôle
  notes.md               LA VÉRITÉ plantée (ground truth)
  seed.sql               La base source synthétique et déterministe
```

## Rejouer une démonstration

```bash
# 1) Charger la base source du scénario (une base Postgres par scénario)
sudo -u postgres bash demo/setup_scenario.sh retail

# 2) Faire rejouer à Noreon le pipeline complet et VOIR ce qu'il trouve
cd backend && python ../demo/verify.py retail
```

`verify.py` connecte Noreon à la base **en lecture seule**, scanne, profile, puis
répond à la question — et imprime la chronologie, l'attribution de la baisse, les
décisions par rôle, la projection d'inaction et la confiance. À comparer au
`gold_standard.md`.

> Données 100 % synthétiques. Aucune donnée réelle, aucune donnée personnelle.

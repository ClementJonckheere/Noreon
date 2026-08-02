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
2. **5 scénarios métier vérifiés** — Retail, CRM, Finance, Supply Chain, RH. **✅ livrés.**
3. **Framework de non-régression** — `Gold Standard → Noreon → écart → score`,
   pour tester chaque évolution du moteur. *(feuille de route — prochaine étape)*

| Domaine       | Dossier         | Question                                   | Cause plantée (trouvée par Noreon) | État |
|---------------|-----------------|--------------------------------------------|---|------|
| Retail        | `retail/`       | Pourquoi le CA baisse-t-il depuis 4 mois ? | Région PACA (97 % de la baisse) | ✅ vitrine |
| CRM           | `crm/`          | Pourquoi le churn augmente-t-il ?          | Canal « Publicité payante » (100 %) | ✅ |
| Finance       | `finance/`      | Pourquoi la marge diminue-t-elle ?         | Ligne « Composants » (92 %) | ✅ |
| Supply Chain  | `supply_chain/` | Pourquoi les ruptures augmentent-elles ?   | « Fournisseur Delta » (97 %) | ✅ |
| RH            | `hr/`           | Pourquoi les départs augmentent-ils ?      | Département « Ingénierie » (100 %) | ✅ |

Chaque cause est **découverte par le moteur** (pas codée en dur), vérifiable par
`python demo/verify.py <scenario>`.

## Le Gold Standard : notre meilleur outil de développement

Pour chaque scénario, on écrit **à la main** ce qu'un excellent analyste
produirait — le meilleur rapport possible (`gold_standard.md`). Puis on compare :

```
Gold Standard  →  Noreon  →  Différences  →  Score
```

L'écart n'est pas un échec : c'est la **liste de courses** du développement. La
bibliothèque a déjà, à elle seule, fait progresser le moteur (ADR D-30/D-31) :

- **Attribution de la variation** (retail) : rapportait la *part du total* (« le plus
  gros segment pèse 80 % » — tautologie) → désormais la *contribution à la baisse*
  (« PACA porte 97 % de la baisse »).
- **Rôles supply chain & RH** (supply, hr) : le Decision Engine ne savait pas quoi
  recommander sur un axe « fournisseur » ou « département » → rôles ajoutés.
- **Piège de détection de mesure** (hr) : une colonne d'ancienneté était prise pour
  une mesure monétaire (le sous-mot « net ») → corrigé.
- **Plafond de crédibilité des impacts** : les fourchettes d'impact ne dépassent
  plus un redressement partiel raisonnable.

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

# CRM — la vérité plantée (ground truth)

**FluxCRM** — SaaS fictif. Tables : `customers`, `churn_events` (le fait).
18 mois (janv. 2024 → juin 2025).

## L'histoire (la cause plantée)
1. Le churn (revenu récurrent perdu / mois) est **stable** jusqu'à l'hiver, puis
   **augmente sur les 4 derniers mois**, de façon accélérée.
2. **Cause dominante : le canal d'acquisition « Publicité payante ».** Ces clients,
   attirés par des promotions, se désabonnent massivement (attentes déçues, faible
   valeur). Sa contribution à la **hausse** du churn est **~ 100 %**.
3. Les autres canaux (Bouche-à-oreille, Référencement, Partenariats) sont **stables**.
4. **Nuance :** ce sont surtout des clients **plan Basic** (faible MRR) — le *nombre*
   de désabonnements grimpe plus vite que le *revenu* perdu.

## Chiffres de référence
| Vérification | Valeur attendue |
|---|---|
| Revenu perdu — début → fin fenêtre | ~ 2 800 € → ~ 3 900 € / mois |
| Nombre de désabonnements / mois | 36 → 71 |
| Contribution « Publicité payante » à la hausse | ~ 100 % |
| Plan dominant des churners « payants » | Basic |

## Pièges volontaires
- Emails invalides (~ 3 %), quelques `revenu_perdu` manquants (complétude).
- FK implicite `churn_events.customer_id → customers.id`.

## Ce qu'une IA médiocre répondrait (et pourquoi c'est faux)
- « Le churn augmente de X %. » → sans cause, inexploitable.
- « La plupart des churners sont en Basic. » → tautologie (Basic est le plus gros
  plan). La vraie cause est le **canal d'acquisition**, pas le plan.

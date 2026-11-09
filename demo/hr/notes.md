# RH — la vérité plantée (ground truth)

**TalentForge** — ESN fictive. Tables : `employes`, `departs` (le fait).
18 mois (janv. 2024 → juin 2025).

## L'histoire (la cause plantée)
1. Les départs (coût de remplacement cumulé / mois) sont **stables**, puis
   **augmentent sur les 4 derniers mois**, de façon accélérée.
2. **Cause dominante : le département « Ingénierie ».** Vague de démissions
   (surcharge + marché tendu). Il porte **~ 100 %** de la hausse. Un ingénieur
   coûte plus cher à remplacer → l'impact financier est amplifié.
3. Les autres départements (Ventes, Support, Marketing) restent **stables**.
4. **Nuance :** sur la fenêtre, le **motif** dominant en Ingénierie est la
   **« Démission »** (et non fin de contrat / retraite).

## Chiffres de référence
| Vérification | Valeur attendue |
|---|---|
| Hausse du coût de remplacement sur la fenêtre | ~ +75 % |
| Contribution « Ingénierie » à la hausse | ~ 100 % |
| Motif dominant (fenêtre, Ingénierie) | Démission (~ 66 % de la hausse) |
| Coût de remplacement d'un ingénieur | ~ 14 000 € |

## Piège technique (rencontré et corrigé)
La colonne d'ancienneté (`ancienneté` en mois) contenait le sous-mot **« net »**,
qui déclenchait à tort la détection de « mesure monétaire » : le moteur sommait
l'ancienneté au lieu du coût. Colonne renommée `duree_poste_mois` → le moteur
choisit bien `cout_remplacement`. *(cf. écart documenté dans README.md)*

## Ce qu'une IA médiocre répondrait
- « Les départs augmentent. » → sans cause.
- « La plupart des départs sont des démissions. » → vrai globalement, mais la
  cause est **départementale** (Ingénierie), pas le motif seul.

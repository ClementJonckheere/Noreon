# Supply Chain — la vérité plantée (ground truth)

**LogiPro** — distributeur fictif. Tables : `entrepots`, `stockouts` (le fait).
18 mois (janv. 2024 → juin 2025).

## L'histoire (la cause plantée)
1. Les ruptures (coût des ventes perdues / mois) sont **stables**, puis
   **augmentent sur les 4 derniers mois**, de façon accélérée.
2. **Cause dominante : le fournisseur « Fournisseur Delta ».** Son délai de
   livraison s'est dégradé : ses SKU tombent en rupture, et les ruptures durent
   plus longtemps. Il porte **~ 97 %** de la hausse.
3. Les autres fournisseurs (Alpha, Beta, Gamma) restent **stables**.

## Chiffres de référence
| Vérification | Valeur attendue |
|---|---|
| Hausse du coût de rupture sur la fenêtre | ~ +115 % |
| Contribution « Fournisseur Delta » à la hausse | ~ 97 % |
| Durée de rupture Delta (fenêtre) | 2–8 jours (vs 1–5 normal) |

## Ce qu'une IA médiocre répondrait
- « Les ruptures augmentent. » → sans cause.
- « L'entrepôt X a le plus de ruptures. » → si réparti, ce n'est pas la cause ;
  la cause est le **fournisseur Delta**, pas un entrepôt.

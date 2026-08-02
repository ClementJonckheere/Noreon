# Finance — la vérité plantée (ground truth)

**Novindus** — industriel fictif. Tables : `clients`, `transactions` (le fait).
18 mois (janv. 2024 → juin 2025).

## L'histoire (la cause plantée)
1. La **marge (€)** est stable, puis **diminue sur les 4 derniers mois**, accéléré.
2. **Cause dominante : la ligne de produits « Composants ».** Le coût
   d'approvisionnement a bondi (fournisseur) : le CA de la ligne tient, mais sa
   **marge s'effondre**. Elle porte **~ 92 %** de la baisse.
3. Les autres lignes (Assemblage, Services, Maintenance) restent **stables**.

## Piège sémantique
`montant_marge = revenue − cout`. La marge peut chuter **sans** que le CA baisse —
c'est le **coût** qui monte. Un analyste junior qui regarde le CA ne voit rien.

## Chiffres de référence
| Vérification | Valeur attendue |
|---|---|
| Baisse de marge sur la fenêtre | ~ −33 % |
| Contribution « Composants » à la baisse | ~ 92 % |
| Taux de marge Composants (normal → fenêtre) | 32 % → ~ 6 % |
| CA Composants | ~ stable |

## Pièges qualité
- Quelques `montant_marge` manquants (complétude), emails invalides.

## Ce qu'une IA médiocre répondrait
- « La marge baisse de 33 %. » → sans cause.
- « Composants génère le plus de marge. » → part du total, pas la cause de la baisse.
- Regarder le **CA** (stable) et conclure « rien d'anormal » → **faux** : c'est le coût.

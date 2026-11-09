# Retail — la vérité plantée (ground truth)

> Ce fichier décrit **la vraie réponse**, connue à l'avance. C'est la référence
> qui permet de dire si Noreon a raison — le fondement du Gold Standard.

## L'entreprise

**Maison Lumière** — enseigne fictive d'équipement de la maison, 6 magasins,
4 régions. 18 mois de données (janv. 2024 → juin 2025).

| Magasin              | Ville     | Région                          |
|----------------------|-----------|---------------------------------|
| Paris Rive Droite    | Paris     | Île-de-France                   |
| Paris Rive Gauche    | Paris     | Île-de-France                   |
| Lyon Presqu'île      | Lyon      | Auvergne-Rhône-Alpes            |
| Lille Grand Place    | Lille     | Hauts-de-France                 |
| **Marseille Prado**  | Marseille | **Provence-Alpes-Côte d'Azur**  |
| **Nice Étoile**      | Nice      | **Provence-Alpes-Côte d'Azur**  |

## L'histoire (la cause plantée)

1. Le CA progresse doucement de janv. 2024 à **février 2025 (pic ~ 41 600 €/mois)**.
2. Puis il **décline pendant 4 mois** (mars → juin 2025), de façon **accélérée** :
   38 470 → 38 165 → 37 295 → 36 257. Soit **−12,8 % depuis le pic**.
3. **Cause dominante : la région PACA s'effondre.** Marseille + Nice perdent
   ~ 14 000 €/mois — soit **~ 97 % de la baisse**. Les autres régions sont stables
   ou en légère hausse.
   → *Origine : un concurrent a ouvert dans la zone (contexte métier).*
4. **Nuance clé (piège de l'analyste junior) :** ce n'est **pas** « moins de clients ».
   - Trafic PACA : 596 → 567 commandes (**−5 % seulement**).
   - Panier moyen PACA : **86 € → 66 € (−23 %)**.
   - Clients actifs au global : stables (290–313/mois).
   → *Le trafic tient, c'est le **panier** qui s'effondre.*
5. **Cause secondaire : rupture d'approvisionnement « High-Tech ».** Quantités
   vendues divisées ~ par 2 dès mars 2025 (462 → 220/mois).

## Les pièges volontaires (pour éprouver le moteur)

- **Piège sémantique** : `orders.amount_ttc` est **TTC** ; `products.net_price` est **HT**.
- **Qualité — Validité** : ~ 2,5 % d'emails invalides (`pas-un-email`).
- **Qualité — Cohérence** : quelques `store_id = 99` orphelins (magasin inexistant).
- **Complétude** : ~ 4 % de montants de paiement manquants (`payments.amount` NULL).
- **FK implicites** (non déclarées) : `orders.store_id → stores.id`,
  `customers.home_store_id → stores.id`, `order_items.product_id → products.id`,
  `payments.order_id → orders.id`. Le scanner doit les retrouver — c'est la
  jointure `orders → stores` qui débloque l'axe **région**.

## Ce qu'une IA médiocre répondrait (et pourquoi c'est faux)

- « Le CA baisse de 8 %. » → vrai mais **sans cause** : inexploitable.
- « La majorité du CA vient des clients *Particulier* / de *Paris*. » →
  **tautologie** : ce sont les plus gros segments, pas la cause de la baisse.
- « Il y a moins de clients. » → **faux** : le trafic tient, c'est le panier.

La bonne réponse isole **la contribution à la baisse** (PACA, 97 %) et distingue
**panier vs trafic**. C'est exactement l'écart que ce scénario a fait apparaître,
et qui a motivé l'**attribution de la variation** (ADR D-30).

## Chiffres de référence (pour vérifier)

| Vérification                         | Valeur attendue           |
|--------------------------------------|---------------------------|
| Pic de CA                            | févr. 2025 (~ 41 570 €)   |
| Dernier mois                         | juin 2025 (~ 36 257 €)    |
| Baisse depuis le pic                 | ~ −12,8 %                 |
| Contribution de PACA à la baisse     | ~ 97 %                    |
| Panier PACA avant → fenêtre          | ~ 86 € → 66 € (−23 %)     |
| Trafic PACA avant → fenêtre          | 596 → 567 (−5 %)          |
| Quantités High-Tech (janv. → mars)   | ~ 462 → 220 (÷2)          |

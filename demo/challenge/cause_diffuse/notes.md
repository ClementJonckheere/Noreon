# Challenge « Cause diffuse » — la vérité

## Le piège
Même schéma que le scénario retail, mais la baisse du CA sur les 4 derniers mois
est **systémique** : le panier moyen recule d'environ **−15 % partout** (tous
magasins, toutes régions, tous segments). Aucune région ne porte plus de ~40 % de
la baisse ; la contribution de chaque axe est simplement **proportionnelle à sa
taille**.

## La bonne réponse
> « La baisse est **généralisée**, pas localisée. Cherchez une cause **transverse**
> (politique de prix, saisonnalité, contexte macro) plutôt qu'un magasin ou une
> région. »

## Pourquoi c'est piégeux
Une baisse uniforme touche **mécaniquement** le plus gros segment le plus fort.
Avant correction, le moteur (qui cherchait la plus forte *contribution*) répondait :

> « la baisse est portée à 93 % par « Particulier » (segment) »

C'est **vrai arithmétiquement** mais **faux analytiquement** : Particulier n'est pas
une *cause*, c'est le plus gros seau. Recommander une « campagne de réactivation
Particulier » n'aurait servi à rien.

## Ce que le challenge a appris au moteur (ADR D-33)
Introduction du **lift** = part dans la variation ÷ part dans la base. Un segment
n'est une **cause** que s'il varie **plus que sa taille ne le voudrait** (lift ≥ 1.5).

- Baisse uniforme → tous les lifts ≈ 1 → aucune cause → « baisse **généralisée** ».
- Baisse localisée (retail) → PACA a un lift ≈ 3 → cause identifiée.

Le moteur ne se laisse plus piéger par la taille des segments.

## Vérifier
```bash
cd backend && python ../demo/verify.py challenge/cause_diffuse
# → « la baisse est GÉNÉRALISÉE : aucun segment ne se détache »
cd backend && python ../demo/benchmark.py --challenge
# → cause_diffuse : APPRIS ✅
```

# Le challenge de l'analyste humain

> On ne mesure plus si Noreon a **raison** — on mesure la **valeur** qu'il apporte
> face à un vrai Data Analyst.

Prends un dataset. Donne-le à un analyste compétent, 45 minutes. Puis compare —
non pas la seule réponse, mais **tous les critères** d'un livrable d'analyse.

```bash
cd backend && python ../demo/human_challenge.py retail
cd backend && python ../demo/human_challenge.py retail crm
```

## Exemple — Retail

| Critère | Analyste (~45 min) | Noreon (~10 s) |
|---|:---:|:---:|
| Cause principale | ✅ | ✅ |
| Causes secondaires / signaux | ✅ | ✅ |
| Recommandations actionnables | ✅ | ✅ |
| Projection « et si rien ne change » | ❌ | ✅ |
| Auto-critique (ce qui invaliderait) | ❌ | ✅ |
| Traçabilité (SQL, sources, preuves) | ❌ | ✅ |
| Reproductibilité à l'identique | ❌ | ✅ |
| Contexte métier / causalité terrain | ✅ | ❌ |
| **Temps** | **~45 min** | **~10 s** |

## Comment lire ce tableau

Le but **n'est pas** « Noreon bat l'humain ». C'est de montrer la
**complémentarité** :

- **Ce que Noreon ajoute** : la vitesse (secondes vs demi-journée), et surtout la
  **rigueur que les humains sautent sous la pression du temps** — auto-critique
  explicite, preuves rejouables (chaque chiffre porte son SQL), projection prudente
  de l'inaction, reproductibilité parfaite.
- **Ce qui reste à l'humain** : le **contexte métier** (« un concurrent a ouvert »)
  et le **jugement causal** final. Noreon identifie des corrélations et le dit —
  il ne prétend pas à la causalité certaine.

**Le bon dispositif combine les deux** : Noreon fait en secondes le travail de fond
d'un analyste senior (et le documente mieux), libérant l'humain pour ce qu'il fait
de mieux — décider en contexte.

## La ligne de base humaine

Chaque scénario porte un `demo/<scenario>/human_baseline.json` : une estimation
**honnête** de ce qu'un analyste compétent produit dans le temps imparti (pas un
homme de paille). Le côté Noreon est mesuré **en direct** (critères extraits de la
réponse réelle, temps chronométré) par `human_challenge.py`.

> C'est la mesure qui compte vraiment pour un investisseur ou un client : pas
> « est-ce juste ? » mais « **qu'est-ce que ça me fait gagner ?** ».

# Règle n°1 — Noreon est *domain-agnostic*

**Retail est un scénario de démonstration, jamais une primitive du produit.**

Toute fonctionnalité doit fonctionner avec des concepts, entités, métriques,
dimensions et responsabilités **arbitraires**, découverts ou définis dans les
données de l'utilisateur. **Aucun comportement métier ne doit dépendre de noms
tels que magasin, produit, client, région, CA ou PACA.**

Concrètement, dans tout code de moteur (concepts, arbitrage, décision, mesure,
responsabilités) :

- ❌ **Interdit** : un `enum` de concepts (`"revenue" | "active_store" | …`),
  une branche `if concept == "magasin_actif"`, une clé de rôle codée en dur
  (`"Directeur réseau"`), une liste de régions/produits en primitive de logique.
- ✅ **Attendu** : un `SemanticConcept` générique (`id`, `label`, `definition`,
  `scope`, `status`, `definitionVersion`, `physicalMappings`, `dependencies`,
  `owner?`) et un arbitrage qui raisonne sur **un concept** — pas sur un magasin,
  un client ou un produit.

La séquence est universelle :

```
Données connectées
  → concept candidat détecté
  → Noreon propose une définition
  → validation OU ambiguïté (plusieurs définitions plausibles)
  → arbitrage humain (impact de chaque définition + propagation)
  → nouvelle définition en vigueur
  → propagation (réponses, découvertes, rapports concernés)
```

`Magasin actif` (Démo Retail), `Client actif` (SaaS), `Mission active` (conseil),
`Chantier terminé` (artisan), `Commande valide` (e-commerce) sont **le même
objet** pour le moteur. Les fixtures d'un espace de démo peuvent porter des rôles
et des concepts seedés ; le moteur, lui, reste générique.

### Protection automatique

`backend/tests/test_arbitration_domain_agnostic.py` fait tourner
`scan → concepts → ambiguïté → arbitrage → propagation` sur un jeu **SaaS**
(`customers`, `subscriptions`, `invoices`, `events`) **sans aucune table**
`stores` / `products` / `orders`. Il vérifie que le moteur n'émet **que** des
requêtes sur ces tables SaaS et que son code ne contient **ni enum de concepts
ni branche métier codée en dur**. Toute régression vers un couplage Retail casse
ce test.

### Dette connue

`app/services/responsibility.py` et `app/services/decision_engine.py` portent
encore un vocabulaire retail français en dur (rôles, régions, gammes). C'est la
dette à résorber : ces couches doivent recevoir un `BusinessContext`
(acteurs, concepts, entités, responsabilités) découvert, et non des primitives
métier codées en dur.

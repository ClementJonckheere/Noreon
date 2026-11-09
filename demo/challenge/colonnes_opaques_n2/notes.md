# Challenge « Colonnes opaques — Niveau 2 » — la vérité

## Le durcissement
Identique au Niveau 1 (colonnes/tables opaques, PACA porte ~97 % de la baisse),
**mais aucune FK n'est déclarée**. Le moteur ne peut donc s'appuyer :
- ni sur les **noms** (`col_002`, `t_s`…),
- ni sur les **métadonnées de relation** (pas de `REFERENCES`).

Pour atteindre la région (qui vit sur `t_s`), il doit **inférer** la relation
`col_002 → t_s.k0` **par recouvrement de valeurs**.

## Ce que le challenge a appris au moteur (ADR D-37)
Nouvelle inférence `infer_value_overlap` (dans l'adaptateur, au scan) :
une colonne entière, sans relation connue, dont les valeurs sont **incluses** dans
la clé d'une autre table **et en couvrent la quasi-totalité** (≥ 90 %, 0 orphelin),
est une **clé étrangère de fait** — même nommée `col_002`.

**Précision avant rappel** : les seuils stricts évitent le piège classique — un
attribut « âge » (18..72) inclus par hasard dans des identifiants (produits 1..80)
n'est PAS pris pour une FK (il n'en couvre que 69 %). C'est exactement le genre de
faux positif qu'un **anti-benchmark** doit bloquer (cf. le test
`test_relation_inference.py`).

## Résultat vérifié
```
Relations (dont FK implicites) : 3   ← inférées par recouvrement de valeurs
· cause trouvée par la valeur : ✓ (Provence-Alpes-Côte d'Azur · 97,1 %)
· décideur par le concept : ✓ (Directeur réseau, 5★)
```

Valide la propriété **P-05** (relations sans FK) — cf. `demo/PROPERTIES.md`.

## Limite / réglage
L'inférence privilégie la **précision** : une vraie FK n'utilisant qu'une fraction
des clés du parent (< 90 %) ne sera pas retrouvée automatiquement. C'est un
compromis assumé (une fausse relation crée de faux axes ; une relation manquée ne
fait que réduire la portée). Réglable via `coverage_min` / `orphan_tol`.

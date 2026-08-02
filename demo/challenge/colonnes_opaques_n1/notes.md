# Challenge « Colonnes opaques — Niveau 1 » — la vérité

## Le test
C'est **exactement** le scénario retail (PACA porte ~97 % de la baisse du CA), mais
**toutes les colonnes et tables sont renommées en identifiants opaques** :

| Sens réel | Nom opaque |
|---|---|
| `orders` | `t_o` |
| `amount_ttc` | `col_003` |
| `order_date` | `col_z` |
| `customer_id` | `col_001` |
| `store_id` | `col_002` |
| `stores.region` | `t_s.a3` |
| `customers.segment` | `t_c.b6` |

Le moteur **ne peut plus lire les noms**. S'il trouve quand même la bonne réponse,
c'est qu'il comprend les **données**, pas le **vocabulaire du schéma**. C'est la
promesse fondatrice de Noreon.

Niveau 1 = renommage. Les FK restent **déclarées** (une FK est une métadonnée, pas
un nom) : les relations survivent. Le test porte sur la **mesure** et la **cause**.

## La bonne réponse
> Identique au retail : « la baisse est portée à ~97 % par
> Provence-Alpes-Côte d'Azur ». La cause est reconnue **par la valeur du segment**,
> pas par le nom de la colonne.

## Ce que le challenge a appris au moteur (ADR D-34)
Détection **par les données** (et non par le nom) :
- **Mesure** : à défaut d'indice de nom (`amount`, `cout`…), le moteur choisit la
  variable numérique la plus **continue** (le plus de valeurs distinctes), ni clé
  ni FK ni catégorie. → `col_003` reconnu comme la mesure.
- **Identifiant** : une colonne est un identifiant si elle est clé, FK **déclarée**,
  ou un **entier quasi-unique** (distinct_ratio ≈ 1) — même nommée `col_002`. Elle
  est exclue des mesures et des axes.

## Résultat vérifié
```
· mesure trouvée par les données : ✓ (total de col_003)
· cause trouvée par la valeur : ✓ (Provence-Alpes-Côte d'Azur · 97.1%)
```

## Limite connue (prochaine étape)
Le **routage vers un rôle métier** (« Directeur réseau ») dépend encore du **nom**
de l'axe. Sur colonnes opaques, la décision reste **générique** (Directeur
financier). Piste : dictionnaire métier + inférence du type d'axe par les valeurs
(un segment « Provence-Alpes-Côte d'Azur » est une région → réseau).

## Niveaux suivants (feuille de route)
- **N2** : FK **non déclarées** → inférer la relation par **recouvrement de
  valeurs** (les valeurs de `col_002` sont incluses dans `t_s.k0`).
- **N3** : valeurs bruitées (`NULL`/`N/A`/`0`/`-1` = « inconnu ») + synonymes métier
  (client → adhérent, commande → transaction).

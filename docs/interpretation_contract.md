# Contrat stable — `interpretation_json` (Phase 2, C4)

Interface stable entre le LLM planificateur et le reste de Noreon. Ce document
est la référence ; le code fait foi (`app/analysis/contracts.py`,
`app/analysis/schema_models.py`).

## Versions (versionnées SÉPARÉMENT)

| Constante | Sens | Valeur |
|-----------|------|--------|
| `INTERPRETATION_SCHEMA_VERSION` | Structure du document (champs, imbrications, invariants). Portée sur le fil via `plan_schema_version`. | `1.2` |
| `GOAL_TYPES_VERSION` | Vocabulaire fermé des types d'objectifs + leur glossaire (prompt système). | `1.0` |
| `RESOLVED_PLAN_SCHEMA_VERSION` | Structure autonome produite par C6. Portée via `resolved_plan_schema_version`, indépendamment du contrat LLM. | `2.0` |

Bumper l'une n'oblige pas à bumper l'autre : on peut affiner le glossaire des
types sans casser la structure, et inversement. Le JSON Schema envoyé au provider
est estampillé des deux (`title`, `x-noreon-schema-version`,
`x-noreon-goal-types-version`).

**Règle de bump** : toute modification de la *sémantique* du glossaire des types
(interpreter.py) DOIT incrémenter `GOAL_TYPES_VERSION` ; toute modification de la
*structure* (schema_models.py / invariants) DOIT incrémenter
`INTERPRETATION_SCHEMA_VERSION`.

## Échec propre, pas de réparation silencieuse

- Une sortie déclarant une version de structure non supportée est **rejetée**
  (`ContractError("unsupported_schema_version")`) — jamais « adaptée ».
- La **seule** réparation sanctionnée est `repair_goal_ids` (renumérotation des
  `id` d'objectifs en double), appliquée **au bord LLM uniquement**, et
  **uniquement** quand c'est non-ambigu (aucun `depends_on` / `unresolved_terms`
  ne pointe un id dupliqué). Sinon → rejet honnête.
- Toute réparation appliquée est **journalisée** (`logger "noreon.planner.contract"`,
  niveau WARNING, message `planner_repair …`) : c'est le signal de **dérive
  modèle** à surveiller en production.
- Tout le reste de la validation reste **strict** (Pydantic + règles métier à
  codes précis). Aucune règle n'a été assouplie en C4.

## Invariants (rappel)

1. **DAG** : `id` uniques, `depends_on` vers des id existants, pas d'auto-dépendance,
   pas de cycle (Kahn), tri topologique déterministe.
2. **Fanout = un CALCUL** (côté `resolved_plan`, pas côté LLM).
3. **Physique interdit côté LLM** : aucun nom de table/colonne, `join_path`,
   cardinalité ni fanout dans `interpretation_json`.
4. **Sincérité de couverture** : chaque `unresolved_term` est rattaché à son
   `goal_id` et porte `necessity=required|optional`. Le défaut conservateur est
   `required`. `optional` n'est légitime que si le goal conserve un cœur
   analytique résolu permettant une réponse partielle honnête.
5. **Intention compilable** : chaque mesure porte son agrégation exacte ; les
   filtres sont typés ; tri, limite et bloc temporel restent sémantiques côté C4
   puis sont physiquement figés par C6.

## Fixtures de référence

`backend/tests/fixtures/interpretations/*.json` — snapshots figés multi-domaines
(retail, crm, generic), validés par `tests/test_contract_fixtures.py`. Ils
cassent si le contrat change sans bump de version. La clé `domain` de chaque
fixture est une métadonnée de test, hors contrat.

## Ordre de déploiement convenu (après C4)

Le « 100 % » du benchmark vaut pour le corpus de qualification, pas comme preuve
de perfection en production. Séquence prudente retenue :

1. **C4 — contrat stable** *(fait)*.
2. **Intégration chat en shadow / offline fallback + télémétrie** : le plan LLM
   est calculé EN PARALLÈLE du fallback offline existant ; les divergences sont
   enregistrées ; le nouveau routage 20B/120B ne décide PAS encore en prod.
3. **Observation des divergences** (plan LLM vs fallback, réparations journalisées,
   incidents).
4. **Activation progressive** du routage une fois les divergences comprises.

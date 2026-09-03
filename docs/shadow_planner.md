# Shadow Planner (Phase 2, C5)

Le planner LLM est **observé, jamais décisionnaire**. Le fallback reste le seul
chemin qui produit la réponse rendue à l'utilisateur. Aucun résultat, erreur,
timeout ou réparation du planner LLM ne peut modifier, bloquer ou retarder cette
réponse.

## Modes (`NOREON_PLANNER_MODE`)

| Mode | Exécutable en C5 | Effet |
|------|------------------|-------|
| `legacy` | ✅ (défaut) | Fallback seul. Zéro appel planner, coût nul. |
| `shadow` | ✅ | Fallback décide ; le planner est évalué hors du chemin critique, télémétrie écrite. |
| `active` | ❌ | **Refusé** (`unsupported_mode`) — l'activation décisionnaire est une phase ultérieure. |
| `canary` | ❌ | Réservé (contrat futur), refusé de la même façon. |

`active`/`canary` ne se comportent **jamais** silencieusement comme `shadow` :
Noreon log une erreur `planner_mode_unsupported` et n'évalue rien.

## Configuration (préfixe `NOREON_`)

- `PLANNER_MODE` = legacy | shadow
- `PLANNER_SHADOW_SAMPLE_RATE` = [0,1] (défaut 1.0 ; abaissable en réel)
- `PLANNER_SHADOW_TIMEOUT_MS`, `PLANNER_SHADOW_MAX_CONCURRENCY`
- `PLANNER_SHADOW_EXECUTOR` = inprocess | rq
- `PLANNER_SHADOW_STORE_PLAN` (rétention courte du plan complet), `PLANNER_SHADOW_PLAN_RETENTION_DAYS`
- `PLANNER_SHADOW_STORE_SANITIZED_QUESTION` (opt-in ; jamais le prompt brut)

## Non-blocage (garanties structurelles)

1. `dispatch_shadow` est appelé **après** la construction de la réponse et ne
   retourne rien vers le chat → ne peut pas la muter.
2. Tout est sous `try/except` isolé ; le seul effet autorisé est une ligne de
   télémétrie.
3. Exécuteur non bloquant, cap de concurrence, timeout dur ; l'enqueue RQ part
   sur un thread détaché (un Redis lent n'ajoute pas de latence).
4. Le worker ouvre **sa propre** session DB (jamais celle du chat) ; il ne reçoit
   qu'un envelope (IDs + données déjà sanitizées).

## Persistance — trois domaines séparés

- `analysis_plans` = plans réellement utilisés (**non créée** en C5).
- `analysis_runs` = exécutions réelles (**non créée** en C5).
- `planner_shadow_evaluations` = candidats LLM + télémétrie (**seule table créée**).

La pollution de l'historique décisionnel est donc **physiquement impossible**.

## Comparaison (le fallback n'est PAS une vérité terrain)

`comparison_outcome` ∈ `identical` · `equivalent` · `material_divergence` ·
`not_comparable` · `llm_error` · `fallback_error`. Les erreurs LLM/fallback ne
sont **pas** des divergences ; le détail granulaire (`contract_error`,
`network_error`, `provider_error`, `timeout`) vit dans `llm_status`.

Facettes inspectées (structurelles, pas d'égalité JSON) : objectif principal,
types de goals, nombre de goals, graphe de dépendances, unresolved, capabilities.
**`unknown` ≠ `empty`** : un champ non exprimé est `null` (not_comparable), un
ensemble vide est `[]` — distinction portée dans les données pour éviter les faux
accords.

- `required_capabilities` est **provisoire et informatif** jusqu'à C6 (vrai
  CapabilityResolver) — il ne peut PAS provoquer à lui seul une divergence matérielle.
- Les équivalences de types (`count ↔ aggregate`) sont une **règle versionnée**
  (`TYPE_EQUIVALENCE_VERSION`), pas une vérité implicite.

## Versions tracées (attribution d'une dérive)

Persistées à chaque évaluation : `interpretation_schema_version`,
`goal_types_version`, `router_version`, `planner_prompt_version`,
`comparator_version`, `projection_version`. Si le taux de divergence bouge, on
sait si la cause est le modèle, le prompt, le routeur, la projection ou le
comparateur.

## Confidentialité

`question_hash` = **HMAC-SHA256** tenant-scoped (secret serveur) — pas un simple
SHA attaquable par dictionnaire. Le prompt brut n'est jamais conservé ;
`question_sanitized` est opt-in. Sampling **déterministe** par `request_id`
(aucun `random`) → reproductible.

## Réparations

`repair_goal_ids` reste la **seule** réparation autorisée. Chaque application :
(1) émet un WARNING (`noreon.planner.contract`) ; (2) est persistée
(`repair_applied`, `repair_type`, `repair_details_json`) → suivi du repair rate
par modèle et détection de dérive.

## Câblage C6 (trois étages distincts)

Depuis le câblage C6, le worker shadow travaille sur le **vrai contexte** du
space/connection (catalogue + `ResolutionContext` construits ENSEMBLE depuis la
DB, refs cohérentes) et persiste trois étages séparés :

1. **`llm_plan_json`** (interpretation) — ce que le LLM a compris.
2. **`capability_resolution_json`** + **`resolved_plan_json`** (C6) — ce que Noreon
   sait réellement satisfaire (états available/reserve/unresolved/blocked, grain,
   fanout, join path validé, stratégie anti-double-comptage).
3. **`legacy_execution_projection_json`** — ce que le legacy a **réellement exécuté**
   (agrégations, GROUP BY, jointures, count(*) vs count(distinct), pré-agrégation),
   projeté depuis le SQL réel, pas depuis le texte de la réponse.

Rétention : étages 1–3 en rétention courte (`plan_purge_after`) ; projections,
comparaison, résumé capability et sécurité analytique durables.

### Sécurité analytique (`analytical_safety`)

Verdicts `same_safety | llm_safer | fallback_safer | not_comparable`
(`ANALYTICAL_SAFETY_VERSION=1.0`). Définition **restrictive** : `llm_safer`
seulement sur une différence **observable et déterministe** — ex. C6 impose
`pre_aggregation` là où le legacy fait un `SUM` après `1→n` sans protection, ou
C6 impose `count_distinct` là où le legacy fait `count(*)`. Jamais parce que C6
porte plus de métadonnées. `llm_safer`/`fallback_safer` sont des signaux
d'**investigation** (revue humaine prioritaire), **pas** une base d'activation :
le legacy peut avoir une protection que la projection n'a pas su reconnaître.

Les capabilities ne deviennent **matérielles** que si comparables des deux côtés
(sinon `not_comparable`, jamais de divergence artificielle).

## Campagne réelle (dev/staging)

```bash
export NOREON_PLANNER_MODE=shadow
export NOREON_PLANNER_SHADOW_SAMPLE_RATE=1.0
# + config OVH (NOREON_OVH_BASE_URL, NOREON_OVH_MODEL_MAIN/SIMPLE, OVH_AI_ENDPOINTS_ACCESS_TOKEN)
# poser ~30–50 questions : simples, multi-objectifs, ambiguës, impossibles
python scripts/shadow_report.py            # rapport de campagne
```

Le rapport décompose LLM contract, comparaison, résolution capability, sécurité
analytique et routage, puis détaille divergences matérielles, écarts de sécurité,
réparations et erreurs. Le fallback reste une **comparaison**, jamais la vérité
terrain.

## Critères d'activation `shadow → (canary) → active`

À décider sur **preuves**, sans traiter le fallback comme vérité terrain, sur une
fenêtre d'observation :

- **contract success rate** (≥ seuil) ;
- **repair rate par modèle** (stable/faible ; dérive = alerte) ;
- **provider/network error rate** ;
- **accord sur objectif principal** ;
- **accord capabilities** — *à partir de C6 seulement* ;
- **taux de divergences matérielles** — avec **revue humaine échantillonnée**
  (`review_status = sampled_for_review`) ;
- **sécurité/injection** : 0 référence inventée ;
- **latence** et **coût**.

Le « 100 % » du benchmark vaut pour le corpus de qualification, pas comme preuve
de perfection en production : c'est précisément ce que le shadow mesure en réel.

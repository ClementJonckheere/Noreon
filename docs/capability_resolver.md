# CapabilityResolver (Phase 2, C6)

Couche **domain-agnostic** entre `interpretation_json` (intention, sortie LLM) et
le PlanCompiler (exécution). Elle traduit l'intention en **exigences résolues**
contre concepts/entités/mesures/**relations validées**, qualité et permissions —
et produit le `resolved_plan_json` (contrat C1). `goal_type ≠ capability`.

**Rien n'est jamais inventé.** Une mesure/dimension/relation absente ⇒ `unresolved`.

## Deux artefacts couplés

- `CapabilityResolution` (riche) : par goal, des `CapabilityRequirement` avec
  `state`, `cause_class`, `reason`, `reserve`, `strategy` → narration / coverage / shadow.
- `resolved_plan_json` (contrat C1, **validé** par `validate_resolved`) : `status`,
  `physical`, `join_path`, `grain`, `method`, `coherence.covers_question(computed_by=noreon)`
  → consommé par le PlanCompiler.

## Grain & fanout — primitives de 1er ordre

- **Fanout formalisé par multiplicité** : une traversée multiplie le flux ssi son
  côté « to » est *many* (`one_to_many` ou `many_to_many`). `creates_row_multiplication`
  se **calcule** ; ce n'est pas un label.
- **Une jointure valide n'est pas une agrégation sûre** : même une relation
  `validated` en `1-n` impose `requires_pre_aggregation`. Le contrat interdit tout
  `fanout_without_pre_aggregation`.
- **Pré-agrégation prouvée sûre ≠ réserve** : mesure additive, grain connu ⇒
  `strategy=pre_aggregation`, état `available` (la réserve est réservée aux caveats).
- **Semi-additivité explicite** : `additivity ∈ {full, semi, non}`. Semi sur un axe
  non-additif ⇒ `semi_additive` + `reserve`. Non-additive ⇒ jamais sommée ⇒ `unresolved`.
- **Grain de mesure inconnu sous fanout** ⇒ `unresolved` (jamais une somme fausse).
- **Dénombrement d'entités sous fanout** ⇒ `count_distinct` sur la clé de grain.

## Join paths — safety-first

Uniquement des relations **system-validated** : `status=validated` **OU**
`origin=constraint` (une FK physique confirmée est autoritaire ; l'inféré non).
Tri **sûreté d'abord** (moins de fanout, éviter `n-n`) puis brièveté puis
coverage/uniqueness. Aucun chemin ⇒ `unresolved(no_validated_relation)` ; chemins
également sûrs et courts ⇒ `NEEDS_CLARIFICATION` + alternatives.

## États et causes (axes séparés)

| État | Sens | cause_class |
|------|------|-------------|
| `available` | exigence satisfaite | — |
| `available_with_reserve` | exploitable avec caveat | `capability` \| `quality` |
| `unresolved` | structure **manquante** (jamais inventée) | `capability` |
| `blocked` | inexploitable | `access` (not_permitted / source_unreachable) \| `quality` (hard-stop) |

- **`available` distinct de `access`** : deux axes orthogonaux (`capability_state`
  et `access_state`). Une donnée peut être capability-disponible mais accès-bloquée.
- **Qualité** : *stale* dans tolérance ⇒ `reserve(quality)` ; hard-stop (score sous
  seuil, ou `staleness_mode=strict`) ⇒ `blocked(quality)` — **jamais** `unresolved`.

## CapabilityCatalogAdapter

Le resolver ne consomme que du `ResolutionContext` **canonique**. Le
`CapabilityCatalogAdapter` normalise tout catalogue non canonique (snapshot DB,
fixtures, cardinalités `n-1|1-1|1-n|n-n` → canonique). Domain-agnostic : aucun nom
métier dans le paquet `app/analysis/capability`.

## Frontière C6 ↔ PlanCompiler

- **C6 décide** : faisabilité, grain, `join_path` validé, **stratégie anti-fanout**
  (`requires_pre_aggregation` = instruction contraignante), méthode (name/version/params).
- **C7 (compiler) exécute** : LogicalQueryIR → SQL par dialecte, applique la
  pré-agrégation imposée, garde-fous. Il ne redécide jamais un `join_path` ni un fanout.
- Contrat de passage : `validate_resolved` doit passer.

## Effet sur le comparateur shadow (C5, #7)

`required_capabilities` devient **matérielle** pour le comparateur **uniquement**
quand la résolution C6 existe des DEUX côtés (`capabilities_provisional=false`) ;
informative sinon. `COMPARATOR_VERSION`/`PROJECTION_VERSION` → 1.1. Le fallback
n'ayant pas de plan, ses capabilities restent provisoires ⇒ jamais de faux
matériel tant que les deux côtés ne sont pas résolus.

## Tests

- **Anti-fanout (prioritaires)** : `1-n`/`n-n` ⇒ pré-agg ; `n-1` ⇒ sûr ; jointure
  valide ≠ agrégation sûre ; count ⇒ `count_distinct` ; grain inconnu ⇒ unresolved ;
  non-additive ⇒ unresolved ; semi-additive sur axe non-additif ⇒ reserve.
- **États/causes** : mesure absente ⇒ unresolved ; FK inférée ⇒ unresolved / FK
  constraint ⇒ résout ; stale ⇒ reserve / strict ⇒ blocked(quality) ; hard-stop
  qualité ⇒ blocked ; ref masqué ⇒ blocked(access) tout en restant capability-available ;
  source injoignable ⇒ blocked ; chemin ambigu ⇒ clarification.
- **Multi-domaines** (retail/saas/solo) + absence de littéral métier dans le paquet.

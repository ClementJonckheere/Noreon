# Décision — modèles du planificateur d'analyse (Phase 2, C3b)

**Statut : DÉCIDÉ** (benchmark réel OVHcloud AI Endpoints).
Le routage de PRODUCTION reste **désactivé** jusqu'à son câblage explicite
(phase ultérieure). Ce document fige le choix et ses preuves.

## Décision

| Rôle | Modèle | Périmètre |
|------|--------|-----------|
| **Principal** | `gpt-oss-120b` | Toutes les demandes |
| **Simple** | `gpt-oss-20b` | Sous-ensemble strict (count / aggregate / ranking mono-objectif), via l'allowlist déterministe + escalade auditée du routeur |

Configuration par variables d'environnement uniquement (aucune clé dans le dépôt) :
`NOREON_OVH_BASE_URL`, `NOREON_OVH_MODEL_MAIN=gpt-oss-120b`,
`NOREON_OVH_MODEL_SIMPLE=gpt-oss-20b`, `OVH_AI_ENDPOINTS_ACCESS_TOKEN`.

## Preuves (53 cas × 2 runs × 5 catalogues)

Les deux modèles sont **qualifiés sur les 5 catalogues** (seuils éliminatoires :
≥ 99 % de JSON conforme, ≥ 95 % de rappel, 0 référence inventée, 0 substitution
silencieuse).

| Catalogue | 120b | 20b | Rappel | JSON | Accord 20b↔120b (simples) |
|-----------|------|-----|--------|------|---------------------------|
| retail_full    | qualifié | qualifié | 1.000 | 100 % | 100 % |
| retail_partial | qualifié | qualifié | 1.000 | 100 % | 100 % |
| crm            | qualifié | qualifié | 1.000 | 100 % | 100 % |
| generic        | qualifié | qualifié | 1.000 | 100 % | 100 % |
| injection      | qualifié | qualifié | sécurité seule | 100 % | — |

- **Sécurité** : `out_of_catalog = 0` sur tous les catalogues, JSON injection
  100 % → aucun modèle n'invente de référence ni ne suit une instruction injectée.
- **Latence** : le 120b est ici **plus rapide** que le 20b (~9–14 s vs ~16–18 s) —
  le 20b n'est retenu que pour le périmètre simple, par principe de coût/simplicité.
- **Résidus** : uniquement des `ReadTimeout` réseau transitoires (séparés de la
  conformité) et des cas hors-domaine (non-sémantiques par conception).

## Comment reproduire

```bash
# variables d'env (token via .env local, jamais commité)
python scripts/bench_planner.py \
  --main gpt-oss-120b --simple gpt-oss-20b \
  --catalog retail_full --catalog retail_partial --catalog crm \
  --catalog generic --catalog injection \
  --runs 2 --split all --out bench_report.json
python scripts/bench_summary.py  bench_report.json
python scripts/bench_diagnose.py bench_report.json
```

## Calibrage du harnais (établi pendant C3b)

Le premier run éliminait les deux modèles ; l'analyse attendu-vs-produit a montré
que c'était l'instrument, pas les modèles. Corrections appliquées, chacune
défendable indépendamment :

1. **Prompt** — glossaire des 10 types d'objectifs (générique, domain-agnostic) ;
   règle d'unicité des `id`.
2. **Scoring** — couverture slot par slot (plus d'« objectif principal » fondé sur
   la priorité) ; substitution uniquement si AUCUN type demandé n'est produit ;
   équivalence `count`↔`aggregate` ; `accept_types` crédités au rappel en
   mono-intention seulement.
3. **Corpus** — croisements/ambiguïtés/causal/entonnoir relabellisés avec leurs
   équivalents défendables ; `affinity` = co-occurrence stricte.
4. **Pairage par domaine** — un cas n'est jugé sur le TYPE que si son domaine ==
   celui du catalogue ; l'anti-hallucination reste éliminatoire partout.
5. **Robustesse** — `repair_goal_ids` (renumérotation sûre des `id` en double au
   point d'entrée LLM) ; préflight résilient aux hoquets réseau ; catalogue
   `injection` en sécurité seule.

Le contrat de validation est resté **strict** (aucune règle assouplie) ; les
corrections portent sur le prompt, le scoring, le corpus et une réparation de
bord non-ambiguë.

# Noreon — Architecture technique

> Data Analyst IA autonome pour le mid-market européen multi-sources.
> Ce document décrit l'architecture telle qu'implémentée (V0.1 → V1.0).

---

## 1. Vue d'ensemble

Noreon comprend automatiquement une ou plusieurs bases, en évalue la qualité,
co-construit un modèle métier validé par l'humain, et répond à des questions en
langage naturel par des analyses **fiables, argumentées, auditables** — sans
jamais exposer de données brutes identifiantes à un LLM.

```
┌────────────┐     HTTP/JSON      ┌──────────────────────────────────────────┐
│ Frontend   │ ─────────────────► │ Backend FastAPI                          │
│ Next.js 14 │  Bearer JWT        │  ├─ API (auth, connexions, chat, …)      │
│ (App Router│                    │  ├─ Services métier (scan, profil, chat…)│
│  + ECharts)│ ◄───────────────── │  ├─ Couche LLM (abstraction fournisseurs)│
└────────────┘                    │  └─ Couche Sources (abstraction moteurs) │
                                   └───────┬───────────────────┬──────────────┘
                                           │ interne           │ lecture seule
                                   ┌───────▼───────┐   ┌───────▼───────────────┐
                                   │ PostgreSQL    │   │ Sources clientes      │
                                   │ (métadonnées, │   │ PostgreSQL / MySQL /  │
                                   │ profils, logs,│   │ CSV / Excel (SQLite)  │
                                   │ users…)+Redis │   └───────────────────────┘
                                   └───────────────┘
```

Deux principes structurants, matérialisés par **deux couches d'abstraction** :

- **Abstraction LLM** (`app/llm/`) — aucun code métier ne dépend d'un
  fournisseur ; on peut basculer OpenAI / Anthropic / Mistral / heuristique
  hors-ligne par configuration.
- **Abstraction des sources** (`app/services/sources/`) — le scanner, le
  profileur, le chat, la qualité et les alertes fonctionnent à l'identique sur
  PostgreSQL, MySQL, CSV et Excel.

---

## 2. Stack technique

| Couche | Technologies |
|---|---|
| Frontend | Next.js 14 (App Router), React 18, Tailwind, **ECharts** |
| Backend | **FastAPI**, SQLAlchemy 2, Alembic, Pydantic v2 |
| Base interne | PostgreSQL (+ pgvector prévu V0.2+), Redis (files de tâches) |
| Orchestration async | worker RQ (repli in-process sans Redis) |
| Abstraction LLM | interface unique multi-fournisseurs, config par tenant |
| Sources | psycopg (PG), PyMySQL (MySQL), sqlite3 + openpyxl (fichiers) |
| Sécurité | AES-256-GCM (secrets), PBKDF2 (mots de passe), JWT HS256, TOTP |

Dépendances de sécurité volontairement limitées : le hash de mot de passe, le
JWT et le TOTP sont implémentés avec la **bibliothèque standard** (voir
`decision-log.md`, D-09).

---

## 3. Backend — organisation

```
backend/app/
├── core/            config, db (session interne), security (AES-256), auth
│                    (PBKDF2/JWT/TOTP), logging (redaction des secrets)
├── models/          ORM interne (tenant, connection, schema_catalog, profile,
│                    quality, semantic, definitions, alert, query_log, user)
├── schemas/         DTO Pydantic (I/O API)
├── llm/             base (interface), heuristic (offline), providers (REST),
│                    factory, prompts
├── services/        logique métier ↓
│   ├── sources/     base (SourceAdapter) + postgres / mysql / files + factory
│   ├── scanner.py       introspection versionnée (via adaptateur)
│   ├── profiler.py      profilage portable multi-dialecte
│   ├── sql_guard.py     garde-fous (AST sqlglot) — lecture seule, LIMIT
│   ├── quality.py       score qualité auditable (5 dimensions)
│   ├── semantic.py      compréhension métier + boucle de validation + mémoire
│   ├── definitions.py   mesures/segments réutilisables
│   ├── graph.py         Knowledge Graph
│   ├── analyst.py       rapport d'anomalies hors-ligne
│   ├── charting.py      suggestion de graphique
│   ├── privacy.py       Privacy Engine (pseudonymisation/ré-identification)
│   ├── confidence.py    indice de confiance calibré
│   ├── chat.py          pipeline NL→SQL complet
│   ├── alerts.py        évaluation des alertes
│   └── pii.py           détection de PII
├── worker/          file RQ + jobs (profilage async)
└── api/             deps (auth/rôles/accès) + routes/*
```

### 3.1 Base interne (schéma principal)

- `tenants`, `tenant_settings` (pondérations qualité, préférences, config LLM).
- `users`, `connection_access` (Module 11).
- `connections` (secrets chiffrés AES-256-GCM).
- `schema_snapshots` → `db_tables` → `db_columns`, `db_relations` (versionné).
- `column_profiles`, `profiling_jobs`.
- `quality_scores` (colonne/table/relation/base, dimensions auditables JSON).
- `business_concepts`, `concept_mappings` (dictionnaire + boucle de validation).
- `business_definitions` (mesures/segments), `alerts`, `alert_events`.
- `query_logs` (audit immuable des exécutions).

5 migrations Alembic (`0dedc6c7eee7` → `6c77ce12453d`).

---

## 4. Le pipeline de chat (Module 7)

```
question NL
  → contexte (schéma courant + dictionnaire validé + définitions métier)
  → génération SQL (LLM ou heuristique) dans le DIALECTE du moteur
  → clarification si ambigu (ne devine jamais silencieusement)
  → garde-fous (sql_guard) : 1 instruction, DDL/DML bloqué, LIMIT auto
  → EXPLAIN + seuil de coût (par moteur) + timeout + file par connexion
  → exécution LECTURE SEULE (adaptateur)
  → Privacy Engine : pseudonymisation des PII avant analyse
  → agent Analyste : résumé, observations, anomalies, recommandations
  → ré-identification LOCALE dans le rapport
  → indice de confiance calibré + score qualité des tables + graphique
  → audit (query_logs)
```

---

## 5. Couche d'abstraction des sources

`SourceAdapter` (interface) expose : `test_connection`, `check_read_only`,
`introspect`, `fetch`, `run_query` (garde-fous partagés), `compute_integrity`,
et des primitives portables pour le profileur (`quote_ident`, `sample_source`,
`length_of`, `is_numeric_type`). Le `dialect` sqlglot par moteur pilote les
garde-fous et la génération SQL.

| Moteur | Read-only | Introspection | Coût | Échantillonnage |
|---|---|---|---|---|
| PostgreSQL | `default_transaction_read_only` + `has_table_privilege` | `pg_catalog` | EXPLAIN JSON | TABLESAMPLE |
| MySQL/MariaDB | session `READ ONLY` + `SHOW GRANTS` | `information_schema` | EXPLAIN JSON | `ORDER BY RAND()` |
| CSV/Excel | ouverture SQLite `mode=ro` | matérialisation SQLite | — | `ORDER BY random()` |

CSV/Excel sont **matérialisés en SQLite local** (une table par fichier/feuille,
inférence de type) : ils deviennent une vraie source SQL.

---

## 6. Sécurité & confidentialité

- **Lecture seule stricte** : sessions read-only + blocage DDL/DML par AST
  (défense en profondeur), aucune écriture sur les sources.
- **Secrets** chiffrés AES-256-GCM au repos, jamais loggés (filtre de redaction),
  jamais transmis au LLM.
- **Privacy Engine** : détection PII au profilage → pseudonymisation
  déterministe (jetons `EMAIL-001`…) avant LLM → ré-identification locale ; la
  table de correspondance ne quitte jamais le processus.
- **Auth** : PBKDF2-SHA256, JWT HS256, MFA TOTP ; rôles admin/analyste/lecteur ;
  droits par connexion source ; isolation stricte des tenants.
- **Audit** : `query_logs` immuable (qui, quoi, quand, quelle base, résultat).

---

## 7. Abstraction LLM (§6)

`LLMProvider` : `generate_sql(question, schema_context, dialect)` et
`analyze_results(...)`. Implémentations : `HeuristicProvider` (hors-ligne,
règles + dictionnaire métier + définitions), et providers REST (OpenAI,
Anthropic, Mistral) sans SDK propriétaire. La `factory` choisit selon la config
du tenant, avec repli heuristique sûr si la clé manque.

---

## 8. Frontend

App Router Next.js. Pages : `/login`, `/` (connexions multi-moteurs + upload),
`/users` (admin), `/connections/[id]` (espace de travail à onglets : Chat,
Schéma, Graphe, Profils, Qualité, Concepts, Définitions, Alertes, Historique).
Le client API (`lib/api.ts`) envoie le **jeton Bearer** (repli `X-Tenant` en
dev). Graphiques via ECharts avec palette validée accessibilité (CVD/contraste).

---

## 9. Tests

117 fonctions de test (124 cas), pytest. Unitaires (chiffrement, garde-fous,
heuristique, PII, qualité, sémantique, apprentissage, charting, privacy,
analyste, auth) + intégration sur bases réelles (PostgreSQL et MariaDB) et
fichiers (CSV/Excel hors-ligne). Les tests d'intégration se sautent
automatiquement si la source n'est pas disponible.

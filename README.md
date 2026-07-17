# Noreon — Data Analyst IA autonome

> Comprendre. Relier. Éclairer.

Noreon comprend automatiquement une base de données, en évalue le contenu, et
répond à des questions en langage naturel par des analyses **fiables,
argumentées, auditables** — sans jamais exposer de données brutes identifiantes
à un LLM externe.

Ce dépôt contient l'implémentation conforme au cahier des charges (version 2.0).
Périmètre livré : **V0.1 → V1.0 (multi-sources)** — de la connexion PostgreSQL
jusqu'aux définitions métier, aux alertes et au **support multi-moteurs
(PostgreSQL, MySQL/MariaDB, CSV, Excel)** via une couche d'abstraction des
sources. Reste, pour compléter la V1.0 : authentification & rôles, SSO, API
publique.

---

## Ce qui est implémenté

| Module (CDC) | Statut | Détails |
|---|---|---|
| **1 — Connexions** | ✅ | **Multi-moteurs** (PostgreSQL, MySQL/MariaDB, CSV, Excel), test obligatoire, **vérification read-only bloquante** (par moteur), credentials chiffrés **AES-256-GCM**, jamais loggés ni transmis au LLM, isolation par tenant |
| **Multi-sources (V1.0)** | ✅ | Couche d'**abstraction des sources** (`SourceAdapter`) : introspection, profilage, garde-fous et chat identiques sur tous les moteurs ; CSV/Excel matérialisés en **SQLite** local (lecture seule) ; upload de fichier ; NL→SQL dans le **dialecte** du moteur |
| **2 — Scanner** | ✅ | Introspection tables/colonnes/PK/FK, **détection des FK implicites** (`xxx_id`), snapshots **versionnés**, scan incrémental par signature |
| **3 — Profilage** | ✅ | Taux de NULL, distinct, min/max, moyenne, top valeurs, **détection du type réel** (dates en VARCHAR…) et des **PII**, comptes exacts (NULL, invalides), **échantillonnage** au-delà du seuil, exécution **asynchrone** |
| **4 — Score qualité** | ✅ (V0.2) | 5 dimensions **auditables** (complétude, validité, unicité, cohérence, fraîcheur) avec détail chiffré vérifiable ; scores colonne/table/relation/base ; pondérations **par tenant** ; intégrité référentielle réelle (orphelins) ; alimente l'indice de confiance et l'arbitrage entre tables |
| **5 — Compréhension métier** | ✅ (V0.2) | Concepts identifiés depuis les **noms ET le contenu réel** (PII, types profilés) ; **boucle de validation humaine** (proposé/validé/corrigé/rejeté, jamais auto-validé) ; **mémoire entreprise** (décisions conservées, corrections → synonymes réutilisés) ; détection des **variantes piégeuses HT/TTC** avec arbitrage obligatoire ; dictionnaire **exportable CSV/JSON** ; synonymes manuels ; concepts validés injectés dans le moteur SQL et signalés dans la confiance |
| **6 — Knowledge Graph** | ✅ (V0.3) | Graphe **navigable** des entités métier (nœuds = tables + concepts-entités validés, taille = volumétrie, bordure = score qualité) ; relations **documentées** (source déclarée/inférée/validée, **cardinalité mesurée**, taux d'intégrité) ; **boucle de validation** des relations inférées ; sert de contexte au moteur SQL |
| **7 — Chat IA** | ✅ | NL→SQL (agrégats, comptages, **GROUP BY « par X » / « par mois »**), **désambiguïsation** (ne devine jamais silencieusement), transparence complète, score qualité des tables utilisées |
| **9 — Graphiques** | ✅ (V0.2) | Type choisi **automatiquement selon la nature des données** (temporel→courbe, catégoriel→barres/secteurs, distribution→histogramme, 2 mesures→nuage), l'utilisateur peut **forcer un autre type** ; exports **PNG / SVG / CSV** ; repli tableau brut ; palette validée accessibilité (CVD) |
| **10 — Rapport IA** | ✅ (V0.3) | Résumé + observations + **anomalies** (tendance, ruptures >30% entre périodes, valeurs aberrantes >2σ, concentration) + **recommandations**, calculés hors-ligne et chiffrés ; **historique rejouable** ; indice de confiance calibré |
| **§5.1 — Privacy Engine** | ✅ (V0.3) | **Pseudonymisation déterministe** des PII (jetons `EMAIL-001`, `NOM-002`…) avant tout envoi au LLM → analyse sur données pseudonymisées → **ré-identification locale** dans le rapport ; audit des colonnes protégées ; la table de correspondance ne quitte jamais le processus |
| **Définitions réutilisables** | ✅ (V0.4) | **Mesures** nommées (`CA = sum(amount_ttc)`) et **segments** (`client fidèle = ≥3 commandes`) définis une fois, réutilisés dans les questions (« CA par mois », « combien de clients fidèles ») ; prioritaires sur l'interprétation générique |
| **Apprentissage** | ✅ (V0.4) | **Mémoire sémantique inter-connexions** : une décision validée sur une base renforce ou corrige les propositions sur les autres bases du tenant ; activable/désactivable |
| **Préférences** | ✅ (V0.4) | Réglages par entreprise : type de graphique par défaut (appliqué au chat), apprentissage automatique |
| **Alertes simples** | ✅ (V0.4) | Surveillance d'une mesure (définition ou expression) : seuil `>`/`<`, **chute en %** ou variation ; évaluation via les **garde-fous** (read-only, EXPLAIN, timeout) ; historique des évaluations |
| **8 — SQL & garde-fous** | ✅ | Blocage **DDL/DML** (AST), **EXPLAIN + seuil de coût**, timeout, **LIMIT automatique**, file d'exécution par connexion, **journal d'audit immuable** |
| **10 — Indice de confiance** | ✅ | Indice **calibré** (adossé au score qualité réel) accompagné de ses facteurs |
| **§6 — Abstraction LLM** | ✅ | Interface unique multi-fournisseurs (OpenAI, Anthropic, Mistral via REST — **pas de SDK propriétaire**), + provider **heuristique hors-ligne** (fonctionne sans clé) |
Multi-moteurs livrés : **PostgreSQL, MySQL/MariaDB, CSV, Excel** (l'architecture
d'adaptateurs rend l'ajout de SQL Server / Snowflake / BigQuery / API REST
mécanique). Reste pour finaliser la V1.0 : **authentification & rôles, SSO/MFA,
API publique**.

### Score qualité — dimensions (Module 4)

| Dimension | Poids défaut | Base de calcul (auditable) |
|---|---|---|
| Complétude | 30 % | 1 − (NULL / total), comptes exacts |
| Validité | 25 % | % de valeurs conformes au format attendu (email, tél., IBAN, SIRET, date) |
| Unicité | 15 % | distinct / non-null quand l'unicité est attendue (PK, email…) |
| Cohérence | 15 % | intégrité référentielle réelle (taux d'orphelins) |
| Fraîcheur | 15 % | ancienneté de la dernière valeur vs cadence attendue |

Une dimension **non applicable** n'est pas pénalisée (poids renormalisés) ;
chaque score porte son détail chiffré (« Validité 97,8 % (10 emails invalides
sur 462) »). Pondérations configurables via `TenantSettings.quality_weights`.

---

## Architecture

```
Noreon/
├── backend/            FastAPI + SQLAlchemy + Alembic
│   ├── app/
│   │   ├── core/       config, db interne, sécurité (AES-256), logging (redaction)
│   │   ├── models/     tenants, connexions, catalogue schéma, profils, journal
│   │   ├── llm/        couche d'abstraction (base, heuristic, providers, factory)
│   │   ├── services/   connections, scanner, profiler, sql_guard, executor, chat…
│   │   ├── worker/     file RQ (repli in-process sans Redis)
│   │   └── api/        routes FastAPI
│   └── tests/          43 tests (unitaires + intégration sur base réelle)
├── frontend/           Next.js 14 + Tailwind (connexions, schéma, profils, chat)
├── scripts/            seed_demo.sql + setup_demo.sh (base de démo + rôle read-only)
└── docker-compose.yml  db (pgvector) + redis + backend + worker + frontend
```

Couches techniques (CDC §6) : **Frontend** Next.js/React/Tailwind ·
**Backend** FastAPI/SQLAlchemy/Alembic · **Base interne** PostgreSQL/pgvector/Redis
· **Async** worker RQ · **Abstraction LLM** multi-fournisseurs par tenant.

---

## Démarrage rapide

### Option A — Docker (tout-en-un)

```bash
cp .env.example .env
# générer une clé de chiffrement :
python -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
# → coller dans NOREON_SECRET_KEY du .env
docker compose up --build
```

- API : http://localhost:8000  (doc interactive : http://localhost:8000/docs)
- Frontend : http://localhost:3000

### Option B — Local (dev)

Prérequis : PostgreSQL, Python 3.11+, Node 20+.

```bash
# 1) Base de démo + rôle read-only
sudo -u postgres bash scripts/setup_demo.sh

# 2) Backend
python -m venv .venv && source .venv/bin/activate
pip install -e backend
export NOREON_DATABASE_URL="postgresql+psycopg://noreon:noreon@localhost:5432/noreon"
export NOREON_SECRET_KEY="$(python -c 'import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')"
(cd backend && alembic upgrade head)
(cd backend && uvicorn app.main:app --reload)

# 3) Worker (optionnel — sinon repli in-process)
(cd backend && python -m app.worker.run)

# 4) Frontend
cd frontend && npm install && npm run dev
```

Ouvrir http://localhost:3000, créer une connexion vers `noreon_demo`
(utilisateur `noreon_ro` / mot de passe `readonly`), **scanner**, **profiler**,
puis poser des questions dans le **Chat**.

---

## Parcours de démonstration

1. **Connexion** — la création vérifie automatiquement que le compte est en
   lecture seule (alerte bloquante sinon, avec le SQL pour créer un rôle dédié).
2. **Scan** — 6 tables détectées ; les FK déclarées **et inférées**
   (`customers.store_id → stores.id`…) apparaissent avec leur niveau de confiance.
3. **Profilage** — statistiques par colonne, PII repérées (email, téléphone…),
   types réels détectés.
4. **Score qualité** — chaque colonne, table, relation et la base reçoivent un
   score **auditable** avec le détail chiffré de chaque dimension (emails
   invalides, orphelins de FK, fraîcheur…).
5. **Concepts** — « Analyser la sémantique » propose 27 mappings (Client,
   Montant, Email…) avec justification auditable ; les 3 colonnes de montant
   (`amount_ttc` TTC, `net_price` HT, `amount`) déclenchent une **alerte
   d'arbitrage** ; validez/corrigez/rejetez, exportez le dictionnaire.
6. **Graphe** — Knowledge Graph navigable ; les relations inférées (avec
   cardinalité et intégrité) se valident d'un clic.
7. **Chat** — « montant total des commandes par mois » →
   `date_trunc('month', …) GROUP BY`, **courbe automatique** (exports PNG/SVG/CSV),
   **rapport d'anomalies** (« baisse -91 %, valeur atypique sur 2025-07 »),
   bandeau **Privacy Engine** sur les questions touchant des PII, et **transparence**
   (SQL, tables + score qualité, colonnes, hypothèses, temps).
8. **Définitions** — créez la mesure « CA » = `sum(amount_ttc)` et le segment
   « client fidèle » ; le chat résout alors « CA par mois » et « combien de
   clients fidèles » via ces définitions.
9. **Alertes** — surveillez « chute du CA de plus de 20% » ou « plus de 100
   clients » ; l'évaluation passe par les garde-fous et s'historise.
10. **Historique** — chaque analyse est tracée (audit immuable) et **rejouable**.

---

## Tests

```bash
source .venv/bin/activate
cd backend && python -m pytest        # 119 tests (dont MySQL + CSV/Excel)
```

Les tests d'intégration (`test_integration.py`) s'exécutent sur la base réelle
`noreon_demo` et sont automatiquement ignorés si elle est absente.

---

## Sécurité & confidentialité

- **Lecture seule stricte** : connexions ouvertes en `default_transaction_read_only`,
  blocage syntaxique DDL/DML en défense en profondeur, aucune écriture sur les sources.
- **Credentials** chiffrés AES-256-GCM au repos, jamais loggés (filtre de redaction),
  jamais transmis au LLM.
- **Privacy Engine** : PII détectées au profilage, **pseudonymisées** avant tout
  envoi au LLM, ré-identifiées localement dans la réponse ; la table de
  correspondance jeton ↔ valeur ne quitte jamais le processus.
- **Isolation tenant** sur toutes les entités.

## Limites connues de la V0.1 (transparence)

- Provider LLM par défaut = **heuristique** (couvre comptage, agrégats, listes,
  top N) ; brancher une clé OpenAI/Anthropic/Mistral pour le NL→SQL complet.
- Authentification complète (SSO, rôles, MFA) prévue en V1.0 — le tenant est
  résolu via l'en-tête `X-Tenant`.
- Tunnel SSH : champ d'option présent, implémentation prévue ultérieurement
  (SSL/TLS opérationnel).
- L'agent Analyste fonctionne **hors-ligne** (tendances, anomalies, concentration
  calculées) ; brancher une clé LLM enrichit l'interprétation en langage naturel.
- Apprentissage avancé et alertes proactives : V0.4.

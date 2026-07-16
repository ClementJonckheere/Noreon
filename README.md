# Noreon — Data Analyst IA autonome

> Comprendre. Relier. Éclairer.

Noreon comprend automatiquement une base de données, en évalue le contenu, et
répond à des questions en langage naturel par des analyses **fiables,
argumentées, auditables** — sans jamais exposer de données brutes identifiantes
à un LLM externe.

Ce dépôt contient l'implémentation **V0.1** conforme au cahier des charges
(version 2.0). Périmètre V0.1 : **PostgreSQL**, scan automatique, profilage
échantillonné, chat SQL avec garde-fous d'exécution et transparence.

---

## Ce qui est implémenté (V0.1)

| Module (CDC) | Statut | Détails |
|---|---|---|
| **1 — Connexions** | ✅ | Test obligatoire, **vérification read-only bloquante**, credentials chiffrés **AES-256-GCM**, jamais loggés ni transmis au LLM, SSL/TLS (`sslmode`), isolation par tenant |
| **2 — Scanner** | ✅ | Introspection tables/colonnes/PK/FK, **détection des FK implicites** (`xxx_id`), snapshots **versionnés**, scan incrémental par signature |
| **3 — Profilage** | ✅ | Taux de NULL, distinct, min/max, moyenne, top valeurs, **détection du type réel** (dates en VARCHAR…) et des **PII**, **échantillonnage** au-delà du seuil, exécution **asynchrone** (worker + file de priorité) |
| **7 — Chat IA** | ✅ | NL→SQL, **désambiguïsation** (ne devine jamais silencieusement), transparence complète |
| **8 — SQL & garde-fous** | ✅ | Blocage **DDL/DML** (AST), **EXPLAIN + seuil de coût**, timeout, **LIMIT automatique**, file d'exécution par connexion, **journal d'audit immuable** |
| **10 — Indice de confiance** | ✅ (partiel) | Indice **calibré** accompagné de ses facteurs (qualité, hypothèses, échantillonnage, couverture) |
| **§6 — Abstraction LLM** | ✅ | Interface unique multi-fournisseurs (OpenAI, Anthropic, Mistral via REST — **pas de SDK propriétaire**), + provider **heuristique hors-ligne** (fonctionne sans clé) |
| **§5 — Privacy Engine** | 🟡 amorce | Détection PII + **masquage** des colonnes sensibles avant envoi au LLM ; anonymisation avancée formalisée en V0.3 |

Roadmap : compréhension métier + boucle de validation humaine + score qualité
(V0.2), Knowledge Graph + rapports + Privacy Engine complet (V0.3),
multi-bases + SSO + rôles (V1.0).

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
4. **Chat** — « Quel est le montant moyen des commandes ? » →
   `SELECT AVG(amount_ttc) …`, résultat, **indice de confiance** et
   **transparence** (tables, colonnes, hypothèses, temps, coût estimé).
5. **Journal SQL** — chaque exécution est tracée (audit immuable).

---

## Tests

```bash
source .venv/bin/activate
cd backend && python -m pytest        # 43 tests
```

Les tests d'intégration (`test_integration.py`) s'exécutent sur la base réelle
`noreon_demo` et sont automatiquement ignorés si elle est absente.

---

## Sécurité & confidentialité

- **Lecture seule stricte** : connexions ouvertes en `default_transaction_read_only`,
  blocage syntaxique DDL/DML en défense en profondeur, aucune écriture sur les sources.
- **Credentials** chiffrés AES-256-GCM au repos, jamais loggés (filtre de redaction),
  jamais transmis au LLM.
- **PII** détectées au profilage et masquées avant tout envoi au LLM.
- **Isolation tenant** sur toutes les entités.

## Limites connues de la V0.1 (transparence)

- Provider LLM par défaut = **heuristique** (couvre comptage, agrégats, listes,
  top N) ; brancher une clé OpenAI/Anthropic/Mistral pour le NL→SQL complet.
- Authentification complète (SSO, rôles, MFA) prévue en V1.0 — le tenant est
  résolu via l'en-tête `X-Tenant` en V0.1.
- Tunnel SSH : champ d'option présent, implémentation prévue ultérieurement
  (SSL/TLS opérationnel).
- Score qualité complet et compréhension métier : V0.2.

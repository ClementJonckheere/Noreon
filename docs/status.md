# Noreon — État du projet & handoff

_Dernière mise à jour : livraison V1.0 (auth & rôles), commit `6af8785`._
_Branche de travail : `claude/project-spec-analysis-q7jtjl` — PR #1._

---

## 1. Résumé exécutif

Tout le périmètre fonctionnel du cahier des charges (v2.0) est implémenté :
**les 11 modules + les chapitres transverses** (§5 sécurité/RGPD, §6
architecture, §7 agents). Le produit tourne de bout en bout sur **PostgreSQL,
MySQL/MariaDB, CSV et Excel**, avec authentification, rôles et droits par source.

- **134 tests** passent (unitaires + intégration sur bases réelles).
- **Analyste approfondi** (au-delà de la sortie de données) : croisements de
  dimensions, facteurs explicatifs et présentation métier (voir D-13).
- **7 versions livrées** en 7 commits (V0.1 → V1.0).
- Reste, comme extensions datées « à venir » dans le CDC : **SSO SAML/OIDC**,
  **API publique**, connecteurs additionnels (SQL Server, Snowflake, BigQuery,
  API REST — mécaniques via la couche d'adaptateurs).

---

## 2. État par module (cahier des charges)

| Module | Statut | Version |
|---|---|---|
| 1 — Connexions (multi-moteurs, read-only, chiffrement) | ✅ | V0.1 / V1.0 |
| 2 — Scanner (introspection, FK implicites, versionné) | ✅ | V0.1 |
| 3 — Profilage (échantillonné, PII, type réel, async) | ✅ | V0.1 |
| 4 — Score qualité auditable (5 dimensions) | ✅ | V0.2 |
| 5 — Compréhension métier + boucle de validation + mémoire | ✅ | V0.2 |
| 6 — Knowledge Graph (cardinalité, validation relations) | ✅ | V0.3 |
| 7 — Chat IA (NL→SQL, désambiguïsation, définitions) | ✅ | V0.1 / V0.4 |
| 8 — SQL & garde-fous d'exécution | ✅ | V0.1 |
| 9 — Graphiques (choix auto, ECharts, exports) | ✅ | V0.2 |
| 10 — Rapport IA (anomalies, recommandations, historique) | ✅ | V0.3 |
| 10+ — Analyste approfondi (croisements, drivers, présentation métier) | ✅ | — |
| 11 — Auth & rôles (MFA, droits par source) | ✅ | V1.0 |
| §5.1 — Privacy Engine (pseudonymisation ↔ ré-identification) | ✅ | V0.3 |
| §6 — Abstraction LLM | ✅ | V0.1 |
| Multi-sources (couche d'adaptateurs) | ✅ | V1.0 |
| Définitions réutilisables, apprentissage, préférences, alertes | ✅ | V0.4 |

---

## 3. Historique des livraisons

| Commit | Contenu |
|---|---|
| `60b72e7` | **V0.1** — PostgreSQL, scan, profilage, chat + garde-fous, transparence |
| `6b8a915` | **V0.2** — Module 4 score qualité auditable |
| `2646816` | **V0.2** — Modules 5 & 9 : compréhension métier + graphiques |
| `3163440` | **V0.3** — Knowledge Graph, rapport IA, Privacy Engine, historique |
| `99027e6` | **V0.4** — définitions réutilisables, apprentissage, préférences, alertes |
| `958168e` | **V1.0** — multi-sources (PostgreSQL, MySQL, CSV, Excel) |
| `6af8785` | **V1.0** — authentification, rôles, MFA, droits par source |

---

## 4. Comment lancer (handoff)

### Bases de démo
```bash
# PostgreSQL interne + source de démo
sudo -u postgres bash scripts/setup_demo.sh
# (optionnel) source MySQL/MariaDB de démo
bash scripts/setup_demo_mysql.sh
```

### Backend
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e backend
export NOREON_DATABASE_URL="postgresql+psycopg://noreon:noreon@localhost:5432/noreon"
export NOREON_SECRET_KEY="$(python -c 'import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')"
(cd backend && alembic upgrade head && uvicorn app.main:app --reload)
```

### Frontend
```bash
cd frontend && npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

### Docker (tout-en-un)
```bash
cp .env.example .env    # renseigner NOREON_SECRET_KEY
docker compose up --build
```

### Tests
```bash
source .venv/bin/activate && (cd backend && python -m pytest)   # 124 tests
```

### Compte de démonstration
- Auth réelle : créer un espace via `/login` (onglet « Créer l'espace »), ou
  `POST /auth/register` (premier utilisateur = admin).
- En dev, sans jeton, l'en-tête `X-Tenant: demo` agit comme admin implicite
  (désactivable par `NOREON_DEV_AUTH_FALLBACK=false`).

---

## 5. Points d'attention pour la reprise

- **Instabilité de l'environnement de dev** utilisé : PostgreSQL et MariaDB
  s'arrêtaient périodiquement (redémarrages fréquents pendant le développement).
  Les scripts `scripts/setup_demo*.sh` rendent les bases reproductibles ; en
  prod, ce point ne se pose pas.
- **pgvector** : prévu pour la mémoire sémantique/embeddings ; non requis par le
  périmètre actuel (l'appariement sémantique est lexical + contenu profilé). Le
  `docker-compose` utilise l'image `pgvector/pgvector`.
- **Provider LLM** par défaut : heuristique hors-ligne (couvre comptage,
  agrégats, GROUP BY « par X / par mois », top N, mesures/segments définis).
  Brancher une clé (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `MISTRAL_API_KEY`)
  active le NL→SQL complet, sans changement de code métier.
- **Fichiers CSV/Excel** : matérialisés en SQLite sous `NOREON_DATA_DIR`
  (défaut `./data`, ignoré par git). Le nom de table dérive du nom d'origine.

---

## 6. Prochaines étapes possibles

1. **SSO SAML/OIDC** (Module 11, « à moyen terme » dans le CDC).
2. **API publique** (V1.0 CDC) + exports programmatiques.
3. **Connecteurs additionnels** : SQL Server, Snowflake, BigQuery, API REST —
   ajout d'un `SourceAdapter` par moteur, le reste est déjà générique.
4. **pgvector + embeddings** pour un appariement sémantique plus fin (Module 5).
5. **Alertes proactives / détection d'anomalies planifiée** (« évolutions
   envisagées » du CDC) en s'appuyant sur l'agent Analyste existant + le worker.
6. **Durcissement** : rotation des clés (KMS/Vault), rate-limiting, journal
   immuable externalisé, tests de non-régression SQL sur jeu métier de référence
   (indicateur de succès « ≥ 90 % de requêtes correctes »).

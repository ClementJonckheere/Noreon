# Noreon — Journal de décisions (ADR)

Décisions d'architecture et leurs justifications, dans l'ordre chronologique.
Format léger : contexte → décision → conséquence.

---

### D-01 — Deux couches d'abstraction (LLM et Sources)
**Contexte.** Le CDC impose l'indépendance vis-à-vis du fournisseur LLM (§6) et
un support multi-bases (V1.0).
**Décision.** Isoler ces deux variabilités derrière des interfaces
(`LLMProvider`, `SourceAdapter`) ; le code métier n'en connaît que le contrat.
**Conséquence.** Ajouter un moteur (MySQL, fichiers) ou un fournisseur (Mistral)
n'affecte ni le scanner, ni le profileur, ni le chat. Refactor PG transparent :
les 109 tests existants sont restés verts après l'introduction de la couche.

### D-02 — Provider LLM heuristique hors-ligne par défaut
**Contexte.** Faire tourner et tester tout le produit sans clé API ni réseau.
**Décision.** Un `HeuristicProvider` (règles + dictionnaire métier + définitions)
génère le SQL pour un sous-ensemble de questions ; repli sûr si une clé manque.
**Conséquence.** Démo et CI 100 % reproductibles. Brancher une clé bascule au
NL→SQL complet sans toucher au code métier. Limite assumée : couverture
linguistique réduite en mode heuristique.

### D-03 — Introspection via `pg_catalog` (et non `information_schema`)
**Contexte.** Bug réel : les vues `information_schema.*constraint*` sont filtrées
par propriétaire et **masquent les FK aux comptes en lecture seule** — pile le
type de compte que Noreon utilise.
**Décision.** Interroger `pg_catalog` pour PK/FK sur PostgreSQL.
**Conséquence.** Les FK déclarées sont vues même en read-only. (Sur MySQL,
`information_schema.key_column_usage` fonctionne pour un compte SELECT.)

### D-04 — Garde-fous SQL par AST (sqlglot), pas par regex
**Contexte.** Bloquer DDL/DML de façon fiable et dialecte-aware.
**Décision.** Parser en AST, refuser les nœuds d'écriture, imposer LIMIT, et
ré-émettre dans le dialecte du moteur.
**Conséquence.** Détection robuste (écriture cachée dans une CTE bloquée),
portable multi-moteurs. Le coût estimé (EXPLAIN) reste spécifique par moteur.

### D-05 — Score qualité : dimensions applicables + renormalisation
**Contexte.** Une colonne texte n'a pas de « fraîcheur » ; la pénaliser fausse le
score.
**Décision.** Chaque dimension est *applicable ou non* ; le score colonne est la
moyenne pondérée des seules dimensions applicables (poids renormalisés), et
chaque dimension porte son détail chiffré vérifiable.
**Conséquence.** Scores auditables et non trompeurs (« Validité 97,8 % (10 emails
invalides sur 462) »), conformes à l'exigence « jamais de justification
générique ».

### D-06 — Validité calculée en Python (portabilité multi-moteurs)
**Contexte.** Le regex SQL diffère (`~` PG, `REGEXP` MySQL, absent SQLite).
**Décision.** Calculer la conformité de format sur un échantillon, côté Python.
**Conséquence.** Validité identique sur tous les moteurs. Sur tables
échantillonnées, la validité porte sur l'échantillon (signalé).

### D-07 — Boucle humaine : les décisions priment sur la ré-analyse
**Contexte.** « Human-in-the-loop » — une correction ne doit pas être écrasée.
**Décision.** Un mapping validé/corrigé/rejeté n'est jamais réécrit par une
nouvelle proposition ; les corrections enrichissent la mémoire (synonymes) et
sont réutilisées, y compris **inter-connexions** (apprentissage tenant).
**Conséquence.** Le moteur « apprend des corrections dès les premiers usages ».

### D-08 — Arbitrage HT/TTC explicite (jamais de fusion silencieuse)
**Contexte.** `net_price` (HT) et `amount_ttc` (TTC) ne sont pas équivalents.
**Décision.** Détecter les variantes de montant et marquer « arbitrage requis »
plutôt que fusionner ; la décision revient à l'humain.
**Conséquence.** Évite des analyses fausses en cascade (risque « mapping
sémantique erroné silencieux » du CDC).

### D-09 — Sécurité en bibliothèque standard (pas de SDK propriétaire)
**Contexte.** Un composant de sécurité doit minimiser sa surface de dépendances.
**Décision.** PBKDF2-SHA256 (mots de passe), JWT HS256 et TOTP RFC 6238
implémentés avec `hashlib`/`hmac`/`struct` ; AES-256-GCM via `cryptography`
(standard de fait). Providers LLM en REST via `httpx`, sans SDK propriétaire.
**Conséquence.** Moins de risque d'approvisionnement ; comportement auditable.
Pour la prod : externaliser la clé maîtresse (KMS/Vault) — voir D-12.

### D-10 — Privacy Engine par pseudonymisation déterministe
**Contexte.** Le LLM doit pouvoir analyser sans voir d'identifiants bruts.
**Décision.** Remplacer les PII par des jetons déterministes (`EMAIL-001`) avant
l'appel LLM, puis ré-identifier **localement** dans le texte produit ; la table
de correspondance ne quitte jamais le processus.
**Conséquence.** Le LLM peut compter/regrouper/référencer les entités ; l'analyse
reste exploitable et l'utilisateur voit les vraies valeurs.

### D-11 — Auth : Bearer JWT + repli dev `X-Tenant`
**Contexte.** Introduire l'auth sans casser l'exploration API ni les tests
existants (qui utilisent `X-Tenant`).
**Décision.** Le principal se résout d'abord via `Authorization: Bearer` ; à
défaut, en dev (`NOREON_DEV_AUTH_FALLBACK=true`), l'en-tête `X-Tenant` agit comme
admin implicite du tenant.
**Conséquence.** Migration douce ; en prod on met le flag à `false` pour exiger
un jeton. Les rôles sont appliqués sur les endpoints mutables ; l'accès par
connexion est vérifié dans `get_owned_connection`.

### D-12 — Fichiers CSV/Excel matérialisés en SQLite
**Contexte.** Traiter des fichiers plats comme une vraie source SQL.
**Décision.** Charger CSV (une table) / Excel (une table par feuille) dans une
base SQLite locale avec inférence de type ; requêtes en `mode=ro`.
**Conséquence.** Scanner, profileur, chat et qualité fonctionnent sans code
spécifique. Le nom de table dérive du **nom d'origine** du fichier (et non du
nom technique d'upload) — correctif appliqué après un bug de nommage.

### D-13 — Analyste approfondi : croisements pilotés par le schéma, hors-ligne
**Contexte.** Restituer le résultat d'une requête, c'est de la « sortie de
données ». La valeur d'un data analyst, c'est de comprendre *qui/quoi* se cache
derrière les chiffres : croiser les variables, isoler les facteurs explicatifs,
présenter des enseignements actionnables.
**Décision.** Après la requête primaire, un service dédié (`deep_analysis.py`)
localise la **table de faits**, choisit une **mesure additive** (jamais un
« âge » sommé : les questions de dénombrement retombent sur l'effectif), énumère
les **dimensions** (colonnes catégorielles, **tranches numériques** — âge,
points —, périodes, et attributs des **tables liées** via les relations du
modèle) puis lance des **requêtes de suivi agrégées** (mêmes garde-fous
lecture seule). Il classe les dimensions par **pouvoir explicatif** (gradient de
la mesure moyenne / concentration), **croise** les deux plus structurantes en
privilégiant un axe « qui » plutôt que le temps, repère les segments atypiques
et rédige contexte / drivers / croisement / points d'attention / recommandations.
**Conséquence.** Réponse à valeur métier (« le panier moyen passe de 246 à 327
selon la tranche d'âge — vrai facteur, pas un total ») sans dépendance LLM ;
tout enseignement est **calculé** et **auditable** (les requêtes de suivi sont
exposées). Les agrégations ne renvoient que des libellés de segments et des
compteurs : **aucune donnée identifiante** ne sort (PII et colonnes quasi-uniques
exclues des dimensions). Best-effort : un échec retombe silencieusement sur le
rapport chiffré standard. Bornage : ≤ 8 requêtes de suivi + 1 croisement.

---

## Dettes / limites connues (à traiter)

- **Concurrence des garde-fous** : le sémaphore « une requête par connexion » est
  in-process ; à porter sur Redis pour un déploiement multi-worker.
- **Clé maîtresse** : lue depuis l'environnement ; passer à un coffre (KMS/Vault)
  et gérer la rotation (D-09).
- **Tunnel SSH** : champ d'option présent, implémentation à faire (SSL/TLS OK).
- **pgvector/embeddings** : appariement sémantique encore lexical + contenu ;
  gain attendu avec des embeddings.
- **Non-régression SQL** : mettre en place un jeu métier de référence pour
  mesurer l'indicateur « ≥ 90 % de requêtes correctes ».

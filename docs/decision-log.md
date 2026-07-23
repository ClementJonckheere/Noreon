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

### D-14 — Historique de chat côté serveur (multi-appareils) + archivage
**Contexte.** Le premier historique de chat était stocké dans le navigateur
(localStorage) : pratique mais non partagé entre appareils/sessions.
**Décision.** Persister l'historique en base interne : `conversations`,
`conversation_folders`, `conversation_turns` (la réponse est mémorisée
sérialisée pour rejouer le fil à l'identique). Scope (tenant, connexion,
utilisateur) — chacun voit son propre historique. Une conversation peut être
**rangée dans un dossier** et **archivée** (masquée sans suppression). Le tour
est créé par un endpoint dédié (`POST …/conversations/{id}/turns`) qui exécute
la question via le pipeline chat ET la mémorise. Sérialisation JSON via
`jsonable_encoder` (dates/Decimal) avant stockage.
**Conséquence.** Historique disponible partout, organisable, archivable. Le
front bascule de localStorage vers l'API sans changer l'expérience « façon
Claude » (composer en bas, liste à droite, dossiers).

### D-15 — Univers → Espaces → BDD + gouvernance des données par espace
**Contexte.** Noreon n'est plus « une entreprise = une BDD » mais un **univers**
(tenant) contenant plusieurs **espaces** d'équipe (CRM, Achat…), chacun
rattachant une ou plusieurs BDD. Une équipe peut voir des données qu'une autre
ne voit pas, et inversement.
**Décision.** Modèle `spaces`, `space_connections` (n-n BDD), `space_members`,
et gouvernance `space_table_access` / `space_column_access`. Politique
**par exception** : tout est visible par défaut, on ne stocke que ce qui est
**décoché** (`enabled=false`). L'admin (DSI) crée les espaces, rattache les BDD,
gère les membres et coche/décoche tables & colonnes — tout le paramétrage est
**réservé aux administrateurs** (`require_admin`) ; un membre n'accède qu'aux
espaces dont il fait partie. Le chat d'espace applique la gouvernance :
tables/colonnes masquées **retirées du contexte** du moteur SQL (il ne peut ni
les proposer ni les interroger) + **blocage en défense en profondeur** si une
requête référence malgré tout une table masquée (`referenced_tables` via AST).
**Croisement multi-BDD** : au niveau de l'analyse (chaque BDD interrogée
séparément, lecture seule + garde-fous), sans fédération SQL — évolution
possible vers un entrepôt commun plus tard.
**Conséquence.** Isolation par équipe + gouvernance fine et auditable, sans
alourdir le stockage. Réutilise tout l'existant (scan, profilage, chat, analyste
approfondi) par simple filtrage du contexte.

### D-16 — Studio de rapports (docs IA) + export Word/PDF
**Contexte.** Au-delà du chat, produire des **livrables** : demander un rapport
sur un sujet, l'éditer, itérer avec l'IA, l'exporter.
**Décision.** Modèle `reports` + `report_blocks` (blocs ordonnés :
markdown | table | chart). Génération **hors-ligne data-backed** : quand une
source est fournie, on lance l'agent approfondi et on transforme la réponse en
blocs (narratif, croisement en tableau, graphique, données) — jamais inventé ;
sans source, un plan à compléter. On peut éditer chaque bloc, réordonner,
supprimer, ajouter du texte, et **pousser une réponse de chat** (narratif +
graphique + tableau) via un bouton « Ajouter à un rapport ». Export **DOCX**
(python-docx), **PDF** (fpdf2) et **Markdown** ; la gouvernance d'espace
s'applique à la génération quand le rapport est rattaché à un espace.
**Conséquence.** Boucle complète « analyser → rédiger → exporter » sans quitter
l'outil, offline. Limite assumée : les graphiques sont exportés en Word/PDF via
leur tableau sous-jacent (pas d'image rendue côté serveur, faute de moteur de
rendu) ; un rendu image ECharts headless est une évolution possible.

### D-17 — Historique de chat par espace + import de BDD depuis l'espace
**Contexte.** Le chat d'espace était sans mémoire, et l'import de BDD passait par
la page Connexions de l'univers.
**Décision.** (a) `conversations` / `conversation_folders` reçoivent un `space_id`
(nullable) et `connection_id` devient optionnel : une conversation appartient
soit à une connexion, soit à un espace ; un tour mémorise la `connection_id`
utilisée (espace multi-BDD). Routes `/spaces/{id}/conversations` (miroir scopé
espace) ; chaque tour choisit sa source et applique la gouvernance de l'espace.
(b) Un formulaire d'import (composant réutilisable) crée une connexion et la
**rattache** aussitôt à l'espace, sans passer par la page Connexions.
**Conséquence.** Chat d'espace multi-appareils avec dossiers/archivage/recherche,
et parcours d'onboarding d'une équipe entièrement dans son espace.

### D-18 — Moteur de raisonnement (agent d'investigation)
**Contexte.** Un NL→SQL unique ne répond pas à une question ouverte
(« pourquoi les ventes baissent ? »). Il faut un vrai agent :
Question → Planification → Sous-questions → Exécution → Synthèse.
**Décision.** `agent.py` : détecte l'intention analytique, choisit le sujet
(table de faits guidée par la question — « ventes » → orders), **planifie** les
axes à examiner (tendance, âge, magasin, produit, ville…) avec une
justification par étape, **exécute** chaque sous-question par une agrégation en
lecture seule (mêmes garde-fous, gouvernance d'espace respectée), en extrait un
**constat chiffré**, puis **synthétise** (facteurs classés, conclusion,
prochaines actions). Câblé en amont du pipeline chat ; repli silencieux si le
sujet ne s'y prête pas. Chaque étape porte SON SQL (transparence « preuve »).
**Conséquence.** Noreon raisonne comme un analyste (plusieurs angles avant de
conclure), hors-ligne et auditable. Honnêteté assumée : l'agent identifie des
**corrélations**, pas des causes certaines (mentionné dans les recommandations).

### D-19 — Suggestions automatiques (« Découvertes »), l'analyste proactif
**Contexte.** À l'ouverture, un vrai analyste ne demande pas « posez votre
question » : il dit déjà ce qu'il a remarqué.
**Décision.** `discoveries.py` agrège HORS-LIGNE des signaux déjà produits :
anomalies/tendance (évolution de la mesure clé — chute mois/mois > 30 %, valeur
> 2σ, variation globale), colonnes suspectes (profils : invalides, NULL élevé),
relations incohérentes (intégrité < 100 %). Chaque découverte porte une
**question de creusement** prête à l'emploi (qui relance le chat / l'agent).
Route `GET /connections/{id}/discoveries`, affichée dans l'état vide du chat.
Respecte la gouvernance d'espace (éléments masqués écartés).
**Conséquence.** L'outil ouvre sur de la valeur (« 2 anomalies, 1 tendance,
1 colonne suspecte, 2 relations incohérentes ») plutôt que sur une page blanche.

### D-20 — « Insights » : hiérarchie, récit et distinction anomalie/opportunité
**Contexte.** Retours produit sur les « Découvertes » : vocabulaire plus premium,
cartes qui *racontent une histoire*, distinction anomalie (problème) vs
opportunité (intéressant), et une hiérarchie de priorité.
**Décision.** Renommage → **Insights**. Chaque trouvaille porte un **niveau**
(🔴 critique / 🟠 important / 🟢 opportunité / ⚪ information) et un **récit**
métier actionnable (pas un chiffre brut). Une **accroche** en tête résume « ce
que j'ai remarqué ». Les hausses deviennent des **opportunités** (catégorie
distincte des anomalies). Tri par niveau.
**Conséquence.** Lecture immédiate de ce qui mérite l'attention ; l'outil ouvre
sur une histoire, pas une page blanche. (Le passage à un raisonnement
**adaptatif** et l'**Analyst Memory** restent des chantiers identifiés — priorité
donnée d'abord au polissage UX/explicabilité, cf. retour « stop aux grosses
fonctionnalités ».)

### D-21 — Sprint polish V1 : explicabilité, accueil, doc
**Contexte.** Retour produit : « la valeur = comprendre, raisonner, **expliquer** ;
stop aux grosses fonctionnalités, place à l'UX/explicabilité/tests/doc ».
**Décision.** (a) **« Pourquoi ces choix ? »** sur chaque réponse : justification
de la **table**, des **colonnes**, de la **jointure** (relation nommée détectée
dans le SQL) et du **graphique** (nature des données). (b) **Accueil
personnalisé** dans les Insights (« Bonjour {nom} — voici ce que j'ai
remarqué »). (c) Doc de statut/handoff rafraîchie.
**Conséquence.** L'explicabilité passe au premier plan (« presque une preuve »),
sans nouvelle grosse fonctionnalité — conforme au retour. Chantiers gardés pour
la suite : raisonnement adaptatif, Analyst Memory (V2), analyse quotidienne.

---

### D-22 — Sprint « aller plus loin » : preuve, refus, observabilité, identité
**Contexte.** Retour produit approfondi : versionner les insights par empreinte,
enrichir la non-régression SQL (familles simple/métier/ambigu/impossible),
transformer la justification en **preuve**, mesurer le produit lui-même, et lui
donner une **identité**.
**Décision.**
- **Insights versionnés par empreinte** : cache clé = `hash(schéma) +
  hash(profils) + hash(qualité)`. Tant que l'empreinte combinée est stable,
  l'insight reste valide (TTL = simple garde-fou). En cas de recalcul, la réponse
  porte `fingerprint` + `stale_reason` (composant modifié) → obsolescence
  **explicable**.
- **Refus honnête (`unanswerable`)** : un filtre portant sur une information
  absente (« clients heureux ») déclenche « Impossible de répondre avec les
  données disponibles » **sans exécuter de SQL**, plutôt qu'un comptage
  silencieux. Détection conservatrice (refus seulement si **tout** le prédicat
  est étranger au schéma). Non-régression organisée en 4 familles.
- **Explicabilité = preuve** : le choix de table est **démontré** (couverture des
  colonnes nécessaires réellement citées, score qualité, concept métier validé)
  — champ `proof`, chaîne de preuve dans « Pourquoi ces choix ? ».
- **Observabilité** : Noreon mesure son propre travail. `telemetry` (compteurs
  LLM/cache en mémoire) + `metrics` (agrégats du journal d'audit) → page
  `/metrics` : **qualité** (temps, confiance, % résolues, % clarifications,
  % SQL validés) et **coûts** (appels/jetons LLM, temps LLM & SQL, cache). Les
  clarifications sont désormais journalisées pour être mesurables.
- **Identité du pipeline** : Discover (Scanner) → Understand (Profiler) →
  Connect (Knowledge Graph) → Reason (Planner/agent) → Reveal (Insights),
  exposée dans l'UI (ruban) et le README.
**Conséquence.** Le produit gagne en **traçabilité** (empreintes), en
**honnêteté** (refus explicite), en **preuve** (explicabilité chiffrée) et en
**auto-mesure** — le tout hors-ligne et sans migration de schéma (compteurs en
mémoire). Le provider heuristique reporte 0 jeton : quand une clé LLM est
branchée, tokens & coût se remplissent sans changement d'API.

---

## Dettes / limites connues (à traiter)

- **Concurrence des garde-fous** : le sémaphore « une requête par connexion » est
  in-process ; à porter sur Redis pour un déploiement multi-worker.
- **Clé maîtresse** : lue depuis l'environnement ; passer à un coffre (KMS/Vault)
  et gérer la rotation (D-09).
- **Tunnel SSH** : champ d'option présent, implémentation à faire (SSL/TLS OK).
- **pgvector/embeddings** : appariement sémantique encore lexical + contenu ;
  gain attendu avec des embeddings.
- **Non-régression SQL** : jeu métier de référence en place (≥ 90 %) + 4 familles
  (simple/métier/ambigu/impossible). Reste à élargir la couverture au fil des
  nouveaux patterns rencontrés en production.
- **Coûts LLM** : jetons/coût réels à 0 tant que le provider heuristique
  hors-ligne est utilisé ; le remplissage devient effectif dès qu'une clé
  OpenAI/Anthropic/Mistral est branchée (l'instrumentation est déjà en place).

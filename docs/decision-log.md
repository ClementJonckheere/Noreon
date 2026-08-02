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

### D-23 — Sprint « analyste de confiance » (A→F)
**Contexte.** Vision produit : Noreon doit se relire, douter, se corriger, se
justifier, connaître l'entreprise et savoir simuler.
**Décision.**
- **A — Validation Engine** (`validation.py`) : « relecture » systématique de
  chaque analyse (mesure HT/TTC, cohérence des dates, NULL, duplication de
  jointure, plausibilité du volume) ; **hypothèses retenues** explicites ;
  **score de fiabilité du rapport** (étoiles + facteurs) ; verdict **« je ne
  peux pas conclure »** (causalité non établie, distinct de « impossible de
  répondre »).
- **B — Le moteur change d'avis** (`agent.py`) : hypothèse de départ confrontée
  au facteur dominant → **auto-révision** ; **journal de raisonnement** horodaté
  (analyses essayées / rejetées / retenues).
- **C — Mesures contradictoires** (`heuristic.py`) : plusieurs montants →
  recommandation **TTC** argumentée, HT explicite respecté ; jamais de fusion
  silencieuse.
- **D — Contexte d'entreprise** (`company_context.py`, migration
  `e5f6a7b8c9d0`) : conventions (TTC, mensuel, périmètre) connues, injectées au
  moteur et affichées en hypothèses — **jamais redemandées**. Priorité :
  question explicite > convention entreprise > défaut TTC.
- **E — Rapport vivant + sources** : la réponse **cite ses sources** (table
  principale/jointe + qualité) et devient consultable couche par couche.
- **F — What if ?** (`simulation.py`) : projection d'un scénario (« panier moyen
  +10% ») avec répartition du gain et **hypothèses affichées** (projection, pas
  prédiction) ; + **métriques d'usage** (`telemetry`, `/metrics/usage`) : quels
  insights/graphiques/concepts/simulations servent le plus.
**Conséquence.** Noreon passe d'« il répond » à « il se relit, doute, se
corrige, se justifie et projette » — tout hors-ligne et auditable. Coût : une
migration légère (contexte entreprise) ; le reste sans schéma (compteurs en
mémoire, calculs à la volée).

---

### D-24 — Evidence Graph, divulgation progressive, auto-critique & chronologie (G→H)
**Contexte.** Retour produit : réunir Pourquoi/Preuve/SQL/Sources en un graphe,
nuancer les preuves, décomposer la confiance — et surtout NE PAS tout afficher en
permanence (risque de fatigue).
**Décision.**
- **G — Evidence Graph** : chaîne logique unique (Question → Hypothèses → Tables
  → Jointures → Preuve → SQL → Résultat → Conclusion) colorée par **niveau de
  preuve** (🟢 forte / 🟡 moyenne / 🔴 faible). **Confidence breakdown** : l'indice
  devient une **somme pondérée** décomposée (qualité 35 / concepts 25 / relations
  18 / SQL 12 / couverture 6 / hypothèses 4). **UI 3 niveaux** (Décision /
  Comprendre / Preuve) pour la divulgation progressive.
- **Unification UX** : la page connexion (rendu plat historique) et le chat
  d'espace partagent désormais le même `AnswerView` à 3 niveaux (fin de la
  duplication).
- **H — Auto-critique** (`self_critique.py`) : section « ce qui pourrait remettre
  en question cette conclusion » fondée sur des signaux RÉELS (colonne de statut
  non filtrée → commandes annulées ; entités de test ; promotion exceptionnelle
  sur une série de revenu ; base HT/TTC ; récence de période ; échantillon /
  troncature). **Chronologie narrée** (`chronicle.py`) : « cette tendance dure
  depuis N périodes » calculée sur la série réelle (streak terminal).
**Conséquence.** Le raisonnement est visualisable et gradué, la confiance est
lisible, et Noreon **affiche ses propres angles morts** — le tout hors-ligne,
sans migration (calculs à la volée), et rangé derrière une divulgation
progressive pour rester lisible.

---

### D-25 — Insight Score + rapports comparables (I)
**Contexte.** Toutes les découvertes se ressemblaient ; rien ne disait ce qui
avait changé depuis la dernière fois.
**Décision.**
- **Insight Score /100** (`discoveries.py`) = 0.30·impact + 0.25·nouveauté +
  0.25·confiance + 0.20·intérêt métier (impact adossé au niveau + magnitude ;
  confiance/nouveauté/intérêt par catégorie). Les insights sont classés par
  niveau puis par score → **les plus intéressants remontent**.
- **Rapports comparables** (`InsightBaseline`, migration `f6a7b8c9d0e1`) :
  chaque insight a une **clé stable** (catégorie|table|colonne|période) ; à
  chaque relevé, on compare à la référence précédente → **nouvelles / corrigées
  / confirmées** (par catégorie), puis on met à jour la référence. « Depuis le
  dernier relevé : 2 nouvelles, 1 corrigée, 3 confirmées. »
**Conséquence.** Les Insights deviennent priorisés et suivis dans le temps —
sans LLM, déterministe ; une seule ligne persistée par connexion.

---

### D-26 — Mémoire du Reasoning Engine (J)
**Contexte.** Chaque investigation repartait de zéro ; le moteur ne capitalisait
pas sur les stratégies qui marchent.
**Décision.** `ReasoningMemory` (migration `a7b8c9d0e1f2`) mémorise, par
(connexion, sujet, dimension), une **efficacité** = moyenne mobile exponentielle
(α=0,4) du « power » observé lors des segmentations. Avant d'analyser, l'agent
**réordonne** les dimensions candidates par efficacité éprouvée (`memory.rank`)
et teste les meilleures d'abord (utile quand le nombre d'étapes est plafonné) ;
après, il **enregistre** le signal observé (`memory.record`). La priorisation est
tracée dans le **journal de raisonnement**.
**Conséquence.** Le moteur apprend quelles chaînes de jointures / dimensions
portent le signal et les teste en priorité — déterministe, borné au tenant, sans
donnée brute. Le chemin chat commit la transaction ; en test, flush + rollback.

---

### D-27 — Rythme narratif, score en mots, intention & Decision Engine (K)
**Contexte.** Retours : raconter le RYTHME (pas juste le fait), traduire le
score en mots, identifier l'objectif de la question, et surtout **adapter les
décisions au rôle**.
**Décision.**
- **Rythme** (`chronicle.py`) : détecte la phase stable initiale et
  l'accélération/ralentissement terminal → « Après une stabilité jusqu'en mars,
  le CA recule progressivement pendant 4 mois, avec une accélération en juillet. »
- **Score en mots** (`discoveries.py`) : `score_label` (Priorité maximale /
  Prioritaire / À surveiller / Mineur) affiché avant le nombre.
- **Objectif** (`decision_engine.detect_intent`) : diagnostic / comparaison /
  reporting / suivi / exploration, exposé sur chaque réponse.
- **Decision Engine** (`decision_engine.py`) : à partir des facteurs dominants
  RÉELS de l'investigation (`Investigation.drivers_struct`), produit des décisions
  **par rôle** — mêmes données, priorités différentes : Finance (marge/coûts),
  CRM (réactivation des segments clients), Réseau (audit local des magasins),
  Produit (assortiment). Le rôle est déduit du vocabulaire de l'axe dominant.
**Conséquence.** Noreon passe de l'analyse à la **décision** : il ne dit plus
seulement « ce qui se passe » mais « que faire, selon qui je suis » — déterministe,
dérivé des données réelles, rangé au Niveau 1 (décision).

---

### D-28 — Decision Engine approfondi : objectif reformulé, impact, journal, inaction (L)
**Contexte.** Retours : reformuler l'objectif, estimer l'impact des actions,
justifier chaque reco, et projeter l'inaction — sans jamais prétendre prédire.
**Décision.**
- **Objectif reformulé** (`restate_intent`) : « diagnostic » → « Diagnostiquer une
  baisse de {mesure} », « comparaison » → « Comparer les performances par {axe} ».
- **Impact estimé** (`_estimate_impact`) : fourchette récupérable = part du facteur
  × |variation| × [0,3 ; 0,6], + niveau de confiance ; toujours étiquetée
  « estimation basée sur la structure historique des données ».
- **Decision Journal** : chaque décision porte sa **justification** (« parce que
  65% de la variation provient de « Store 3 » »).
- **« Et si je ne fais rien ? »** : projection prudente à partir de la cadence
  récente (`chronicle.recent_rate`) sur 3 périodes, **formulée sans certitude**
  (« si la tendance se maintient et qu'aucun changement majeur n'intervient… une
  projection sous hypothèses, pas une prédiction »).
**Conséquence.** La décision devient priorisable (impact), défendable (journal) et
lucide sur le coût de l'inaction — tout en restant rigoureux sur l'incertitude.

### D-29 — Sérendipité, matrice effort/impact, mémoire métier & ton mesuré (M)
**Contexte.** Le moteur devrait parfois **surprendre** (découverte adjacente plus
importante que la demande), **prioriser** les recommandations par rapport
effort/impact, **apprendre** des décisions prises, et garder un **ton mesuré**
(« les données suggèrent que… » plutôt que « je pense que… »).
**Décision.**
- **Sérendipité** (`discoveries.top_side_finding`) : la découverte la plus notable
  **sur une autre table** que le sujet analysé (score ≥ 55), calculée sans requête
  source (relations + profils). Rendue « 🔭 Découverte inattendue — les données ont
  aussi révélé… », jamais une certitude.
- **Matrice effort/impact** : chaque décision porte `effort`, `impact_level` et un
  rang d'**étoiles** `_stars = clamp(3 + impact − effort, 1, 5)` ; la liste est
  triée par priorité décroissante (fort impact + faible effort d'abord).
- **Mémoire métier** (`DecisionRecord` + `decision_memory`) : l'humain qualifie une
  reco (retenue / mise en œuvre / réussie / abandonnée) via
  `POST /connections/{id}/decisions/feedback` (réservé analyste). Une reco proche
  (recouvrement lexical ≥ 40 % sur le même rôle) est ensuite annotée « déjà
  appliquée avec succès dans un contexte similaire » — boucle d'amélioration
  continue. Aucune donnée métier brute stockée (axe d'analyse + rôle + texte).
- **Ton mesuré** : formulations ancrées sur le fait constaté, sans « je pense » ni
  promesse — cohérent avec l'architecture déterministe autour du LLM.
**Conséquence.** Le moteur devient proactif (il signale l'important ailleurs),
actionnable (priorité coût/bénéfice) et cumulatif (il capitalise sur les décisions
passées) — sans jamais imiter une confiance humaine qu'il n'a pas.

### D-30 — Attribution de la variation + bibliothèque de démonstration (N)
**Contexte.** La construction du **scénario vitrine** de la bibliothèque de
démonstration (`demo/retail/`, « Pourquoi le CA baisse depuis 4 mois ? ») a révélé,
via la méthode **Gold Standard**, un manque du moteur : l'investigation rapportait
la **part du total** (« le plus gros segment pèse 80 % » — tautologie) au lieu de
la **contribution à la baisse**. Un analyste senior dit « la baisse vient de PACA »,
pas « la majorité du CA vient de la majorité des clients ».
**Décision.**
- **Attribution de la variation** (`agent._attribute_variation`) : pour une mesure
  en baisse/hausse avec un axe temporel, on compare la **fenêtre récente** à la
  **précédente**, axe par axe, et on classe par **contribution au changement**
  (part de la baisse brute portée par le segment, ∈ [0, 100]). La fenêtre = le
  nombre de périodes consécutives de la tendance (`_trailing_run`).
- **Priorité à la cause du changement** : quand l'attribution est concluante
  (≥ 55 %), elle **remplace** les facteurs de structure dans `drivers_struct` (on
  ne garde un facteur secondaire que s'il est lui aussi concentré ≥ 65 %) ; les
  tranches numériques sont écartées (libellés bruts peu parlants).
- **Decision Engine** : la cause dominante (1er facteur) est **rehaussée d'une
  étoile** pour mener les recommandations (« agir au bon endroit » prime sur « agir
  à faible effort mais hors sujet »).
- **Auto-révision cohérente** : le « changement d'avis » s'ancre sur l'attribution
  (« la structure pointait X, mais la baisse vient de Y »).
- **Bibliothèque de démonstration** (`demo/`) : une base Postgres synthétique et
  déterministe par scénario (`setup_scenario.sh`), un **runner de vérification**
  (`verify.py`) qui rejoue le pipeline et imprime ce que le moteur trouve, et pour
  chaque scénario un **Gold Standard** écrit à la main + les documents attendus
  (raisonnement, SQL, graphiques, rapport, décisions, vérité plantée).
**Conséquence.** Sur le scénario vitrine, Noreon passe de « le plus gros segment
pèse le plus » à **« la baisse est portée à 97 % par la région PACA »**, avec le bon
décideur (réseau) en tête — vérifié end-to-end. Le Gold Standard devient l'outil de
non-régression du moteur.

### D-31 — 5 scénarios métier vérifiés + corrections révélées (Étape 2)
**Contexte.** Extension de la bibliothèque aux 4 domaines restants (CRM, Finance,
Supply Chain, RH), chacun avec une cause plantée et un Gold Standard. La
vérification end-to-end a fait apparaître trois corrections.
**Décision.**
- **5 scénarios** (`demo/crm|finance|supply_chain|hr`) : une base Postgres
  synthétique par domaine, l'axe causal porté par une colonne propre de la table de
  faits (attribution fiable sans jointure). Causes découvertes par le moteur :
  Publicité payante (100 %), Composants (92 %), Fournisseur Delta (97 %),
  Ingénierie (100 %).
- **Rôles supply chain & RH** ajoutés au Decision Engine (`_ROLE_HINTS` /
  `_ROLE_ACTIONS`) : un axe « fournisseur » → *Directeur supply chain* (sécuriser
  l'appro) ; « département » → *Directeur des ressources humaines* (plan de rétention).
- **Faux positif de mesure corrigé** : le sous-mot « net » dans « ancienneté »
  déclenchait la détection de mesure monétaire → colonne de démo renommée
  (`duree_poste_mois`) ; note laissée sur la fragilité de la détection par sous-chaîne.
- **Plafond de crédibilité des impacts** (`_estimate_impact`) : la fourchette
  d'impact récupérable est bornée (≤ +25 à +45 %) — une variation extrême ne produit
  plus « +81 à +162 % ».
- **Cohérence hausse/baisse** de l'auto-révision (le texte disait « baisse » même
  pour une hausse).
**Conséquence.** Cinq démonstrations métier reproductibles et vérifiées, chacune
avec le bon décideur et un impact crédible. La méthode Gold Standard a directement
produit quatre améliorations du moteur.

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

# Propriétés de Noreon (validées par la bibliothèque)

Formulées comme des **affirmations vérifiables** : chacune est adossée à un
scénario ou un challenge reproductible (`python demo/benchmark.py …`). Ce sont les
garanties que le moteur ne dépend pas des artefacts de tes jeux de données.

---

## P-01 — Indépendance au nom de schéma (*Schema Name Independence*)

> Lorsque les noms de tables et de colonnes sont absents, opaques ou non
> descriptifs, Noreon identifie les **mesures**, **dimensions** et **clés** à partir
> des caractéristiques statistiques, des distributions de valeurs et des relations
> observées dans les données.

**Preuve.** `challenge/colonnes_opaques_n1` — scénario retail à l'identique (PACA
porte 97 % de la baisse), toutes les colonnes/tables renommées en opaque
(`col_003`, `a3`, `t_o`). Noreon retrouve la mesure (`col_003`) par son profil et la
cause (« Provence-Alpes-Côte d'Azur ») par la valeur du segment.

**Mécanisme** (ADR D-34) : `is_identifier` (clé/FK/entier quasi-unique par les
données) + détection de mesure par la continuité (plus de valeurs distinctes), à
défaut d'indice de nom.

**Statut : ✅ vérifié.**

---

## P-02 — Responsabilité fondée sur le concept (*Concept-based Responsibility*)

> Le décideur (rôle métier) est déterminé par le **concept** de l'axe — détecté à
> partir des **valeurs** — et non par le nom de la colonne. Un axe opaque dont les
> valeurs sont des régions est routé vers le Directeur réseau.

**Preuve.** Même challenge : l'axe `a3` (opaque) est routé vers **Directeur réseau**
car ses valeurs sont des régions françaises → concept « zone géographique ».

**Mécanisme** (ADR D-35) : le **Responsibility Engine** (`services/responsibility.py`)
mappe `valeurs → concept → responsabilité`, en amont du Decision Engine.

**Statut : ✅ vérifié.**

---

## P-03 — Cause, pas taille (*Causal Lift*)

> Un segment n'est désigné comme cause d'une variation que s'il varie **plus que sa
> taille ne le voudrait** (lift ≥ 1,5). Une baisse uniforme ne produit donc pas de
> faux coupable (« le plus gros segment »).

**Preuve.** `challenge/cause_diffuse` — baisse systémique (panier −15 % partout).
Noreon conclut « baisse **généralisée** » au lieu d'attribuer à tort au plus gros
segment.

**Mécanisme** (ADR D-33) : `lift` = part dans la variation ÷ part dans la base,
utilisé comme garde-fou dans l'attribution.

**Statut : ✅ vérifié.**

---

## P-04 — Attribution de la variation (*Change Attribution*)

> Noreon explique **d'où vient le changement** (contribution à la baisse/hausse),
> et non « d'où vient le total » (tautologie corrélée à la taille des segments).

**Preuve.** Les 5 scénarios métier : la cause rapportée est la contribution à la
variation (PACA 97 %, Publicité payante 100 %, Composants 92 %, Delta 97 %,
Ingénierie 100 %), pas la part du total.

**Mécanisme** (ADR D-30) : fenêtre récente vs précédente, par axe.

**Statut : ✅ vérifié.**

---

## P-06 — Causes multiples (*Multi-cause Attribution*)

> Quand la variation vient de plusieurs foyers concentrés (aucun dominant), Noreon
> les **nomme tous** avec leur contribution — au lieu d'en désigner un seul, ou de
> conclure à tort « baisse généralisée ».

**Preuve.** `challenge/causes_multiples` — baisse répartie sur 3 magasins (~40/35/25 %)
dans 3 régions. Noreon : « 3 foyers — PACA (44 %), ARA (32 %), HdF (20 %) ».

**Mécanisme** (ADR D-36) : contribution + lift de **chaque** segment ; classement de
l'axe en cause unique / multi-foyers / diffuse ; rasoir d'Occam pour choisir l'axe.

**Statut : ✅ vérifié.**

---

## P-05 — Relations sans clé étrangère (*FK-free Relation Inference*)

> En l'absence de FK déclarée et de noms parlants, Noreon retrouve une relation par
> **recouvrement de valeurs** : une colonne dont les valeurs sont incluses dans la
> clé d'une autre table (et en couvrent la quasi-totalité) est une FK de fait.

**Preuve.** `challenge/colonnes_opaques_n2` — colonnes opaques **et aucune FK
déclarée**. Noreon infère `col_002 → t_s.k0`, atteint la région, et attribue la
baisse à « Provence-Alpes-Côte d'Azur » (97 %) → Directeur réseau.

**Mécanisme** (ADR D-37) : `infer_value_overlap` (couverture ≥ 90 %, 0 orphelin) —
précision avant rappel, pour ne pas confondre un attribut (âge) inclus par hasard
dans des identifiants avec une vraie clé étrangère.

**Statut : ✅ vérifié.**

---

## P-07 — Conscience de la saisonnalité (*Seasonality Awareness*)

> Noreon compare une baisse à la **même période l'an dernier** (glissement annuel),
> pas seulement au mois précédent. Si le creux est conforme aux années passées, il
> le déclare **saisonnier** et ne recommande **aucune action corrective**.

**Preuve.** `challenge/saisonnalite` — creux estival qui se répète chaque année.
Noreon : « baisse SAISONNIÈRE ; +4 % en glissement annuel — pas une anomalie »,
sans aucune décision corrective.

**Mécanisme** (ADR D-38) : dès ~ 16 mois d'historique, comparaison de la fenêtre
récente aux mêmes mois de l'année N-1 ; si ≥ −4 %, la baisse est saisonnière →
attribution sautée, décisions supprimées.

**Statut : ✅ vérifié.**

---

## P-08 — Humilité (*Calibrated Abstention*)

> Quand la qualité des données est insuffisante pour une conclusion fiable, Noreon
> **s'abstient honnêtement** — « je ne peux pas conclure avec suffisamment de
> confiance » — plutôt que d'inventer une réponse à partir de données trouées.

**Preuve.** `challenge/qualite_catastrophique` — montants (~ 45 %) et dates (~ 50 %)
majoritairement manquants. Noreon s'abstient et ne produit aucune décision.

**Mécanisme** (ADR D-39) : contrôle de complétude (profilage) de la mesure et de la
date avant toute analyse ; au-delà de 40 % de valeurs manquantes, l'investigation
s'arrête sur un constat de fiabilité.

**Statut : ✅ vérifié.**

---

### Prochaines propriétés visées (challenges à venir)

- **Causalité inversée** : ne pas confondre « les promos font baisser les ventes »
  avec « les promos augmentent PARCE QUE les ventes baissent ».
- **Le challenge de l'analyste humain** : comparer Noreon à un vrai analyste
  (cause principale, causes secondaires, recommandations, auto-critique, temps).

> Chaque propriété validée est un argument technique différenciant : Noreon
> **reconstruit la sémantique à partir des données**, il ne se contente pas de lire
> le schéma.

# Bibliothèque de démonstration Noreon

> Un investisseur, un recruteur, un enseignant ou un client retiendra bien plus
> **une démonstration** qu'une liste de fonctionnalités.

Cette bibliothèque contient des **scénarios métier reproductibles**. Chacun a :

- **une vraie base** (données synthétiques, déterministes, chargées en une commande) ;
- **une vraie histoire** (une cause plantée dans les données — on connaît la réponse) ;
- **une vraie démonstration** (Noreon rejoue le pipeline et on **vérifie** ce qu'il trouve).

## Philosophie : un scénario exceptionnel d'abord

Un scénario irréprochable vaut plus que dix scénarios moyens. On construit donc
dans cet ordre :

1. **Scénario vitrine** — `retail/` *« Pourquoi le CA baisse-t-il depuis 4 mois ? »*
   Poussé au maximum : compréhension → investigation → hypothèses → preuves →
   graphiques → recommandations → projection → Decision Engine → rapport. **✅ livré.**
2. **5 scénarios métier vérifiés** — Retail, CRM, Finance, Supply Chain, RH. **✅ livrés.**
3. **Framework de non-régression** — `Gold Standard → Noreon → écart → score`,
   pour tester chaque évolution du moteur. **✅ livré** (voir plus bas).

| Domaine       | Dossier         | Question                                   | Cause plantée (trouvée par Noreon) | État |
|---------------|-----------------|--------------------------------------------|---|------|
| Retail        | `retail/`       | Pourquoi le CA baisse-t-il depuis 4 mois ? | Région PACA (97 % de la baisse) | ✅ vitrine |
| CRM           | `crm/`          | Pourquoi le churn augmente-t-il ?          | Canal « Publicité payante » (100 %) | ✅ |
| Finance       | `finance/`      | Pourquoi la marge diminue-t-elle ?         | Ligne « Composants » (92 %) | ✅ |
| Supply Chain  | `supply_chain/` | Pourquoi les ruptures augmentent-elles ?   | « Fournisseur Delta » (97 %) | ✅ |
| RH            | `hr/`           | Pourquoi les départs augmentent-ils ?      | Département « Ingénierie » (100 %) | ✅ |

Chaque cause est **découverte par le moteur** (pas codée en dur), vérifiable par
`python demo/verify.py <scenario>`.

## Le Gold Standard : notre meilleur outil de développement

Pour chaque scénario, on écrit **à la main** ce qu'un excellent analyste
produirait — le meilleur rapport possible (`gold_standard.md`). Puis on compare :

```
Gold Standard  →  Noreon  →  Différences  →  Score
```

L'écart n'est pas un échec : c'est la **liste de courses** du développement. La
bibliothèque a déjà, à elle seule, fait progresser le moteur (ADR D-30/D-31) :

- **Attribution de la variation** (retail) : rapportait la *part du total* (« le plus
  gros segment pèse 80 % » — tautologie) → désormais la *contribution à la baisse*
  (« PACA porte 97 % de la baisse »).
- **Rôles supply chain & RH** (supply, hr) : le Decision Engine ne savait pas quoi
  recommander sur un axe « fournisseur » ou « département » → rôles ajoutés.
- **Piège de détection de mesure** (hr) : une colonne d'ancienneté était prise pour
  une mesure monétaire (le sous-mot « net ») → corrigé.
- **Plafond de crédibilité des impacts** : les fourchettes d'impact ne dépassent
  plus un redressement partiel raisonnable.

## Structure d'un scénario

```
demo/<scenario>/
  README.md              Vue d'ensemble + comparaison Gold ⇄ Noreon
  question.md            La question et son cadrage métier
  gold_standard.md       Le rapport IDÉAL, écrit à la main (référence)
  expected_reasoning.md  Le raisonnement attendu, étape par étape
  expected_sql.sql       Les requêtes clés (auditables)
  expected_charts.md     Les graphiques attendus
  expected_report.md     La structure du rapport exportable
  expected_decisions.md  Les décisions attendues par rôle
  notes.md               LA VÉRITÉ plantée (ground truth)
  seed.sql               La base source synthétique et déterministe
```

## Rejouer une démonstration

```bash
# 1) Charger la base source du scénario (une base Postgres par scénario)
sudo -u postgres bash demo/setup_scenario.sh retail

# 2) Faire rejouer à Noreon le pipeline complet et VOIR ce qu'il trouve
cd backend && python ../demo/verify.py retail
```

`verify.py` connecte Noreon à la base **en lecture seule**, scanne, profile, puis
répond à la question — et imprime la chronologie, l'attribution de la baisse, les
décisions par rôle, la projection d'inaction et la confiance. À comparer au
`gold_standard.md`.

## Framework de non-régression (le benchmark)

Chaque scénario porte un `expected.json` — la **projection machine-vérifiable** de
son Gold Standard (intention, sens de la variation, axe causal, segment,
contribution minimale, bon décideur). `benchmark.py` rejoue le moteur et **note
l'écart** sur 100 :

```bash
cd backend && python ../demo/benchmark.py               # bulletin des 5 scénarios
cd backend && python ../demo/benchmark.py retail        # un seul
cd backend && python ../demo/benchmark.py --threshold 90
```

Barème (100 pts) : intention (10) · sens de la variation (15) · **bon axe causal
(25)** · **bon segment (25)** · contribution suffisante (15) · bon décideur ★≥4 (10).

État actuel : **5 / 5 PASS · moyenne 100 / 100** (seuil 80).

Le benchmark tourne aussi en **CI** via `backend/tests/test_benchmark.py` (ignoré
scénario par scénario si la base n'est pas chargée). Si une évolution du moteur
dégrade une démonstration, le test tombe : c'est le filet de sécurité qui protège
la qualité, exactement comme un Gold Standard le doit.

Le bulletin note aussi la **démarche** (pas seulement la réponse) — Plan · Choix
des dimensions · Mesure · Explication · Décision · Efficacité — afin de voir *où* le
raisonnement se dégrade si on modifie le moteur.

## Noreon Challenge — casser le moteur pour le faire progresser

`demo/challenge/` contient des scénarios **adversariaux** : le but n'est pas 100,
c'est que le moteur **apprenne**.

```bash
cd backend && python ../demo/benchmark.py --challenge
```

Challenges livrés :

- **`cause_diffuse`** — baisse systémique sans coupable localisé. Le moteur
  répondait « portée à 93 % par le plus gros segment » (tautologie) ; il répond
  désormais « baisse **généralisée** ». Correction = notion de **lift** (ADR D-33).
- **`colonnes_opaques_n1`** — toutes les colonnes rendues opaques (`col_003`, `a3`…).
  Noreon retrouve la **mesure** (par le profil), la **cause** (« Provence-Alpes-Côte
  d'Azur », par la valeur) **et le décideur** (Directeur réseau, par le **concept** :
  valeurs = régions → zone géographique). Corrections = détection par les données
  (ADR D-34) + **Responsibility Engine** (ADR D-35).

- **`causes_multiples`** — la baisse se répartit sur 3 foyers (~40/35/25 %). Noreon
  les **nomme tous les trois** au lieu d'en désigner un seul ou de conclure « diffus »
  (attribution single / multi / diffuse, ADR D-36).
- **`colonnes_opaques_n2`** — colonnes opaques **et aucune FK déclarée**. Noreon
  **infère les relations par recouvrement de valeurs** (`col_002 ⊆ t_s.k0`) pour
  atteindre la région (ADR D-37).

Voir `demo/challenge/README.md` et `demo/PROPERTIES.md` (propriétés P-01…P-06).

## Pipeline de raisonnement

```
Question → Reasoning Engine → Concepts → Responsibility Engine → Decision Engine
```

Le **Responsibility Engine** (`backend/app/services/responsibility.py`) traduit un
axe en **concept métier** à partir de ses **valeurs** (régions → zone géographique,
noms de fournisseurs → fournisseur…), puis en **responsabilité** (Directeur réseau,
supply chain, CRM…). Le Decision Engine ne raisonne plus sur un nom de colonne mais
sur un concept — d'où la robustesse aux colonnes opaques.

> Données 100 % synthétiques. Aucune donnée réelle, aucune donnée personnelle.

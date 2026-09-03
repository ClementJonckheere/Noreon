# Scénario vitrine — Retail

> **« Pourquoi le chiffre d'affaires baisse-t-il depuis 4 mois ? »**
> Enseigne fictive *Maison Lumière* · base `noreon_demo_retail` · 100 % synthétique.

Le scénario de référence : celui qu'on montre à un recruteur, un investisseur, un
enseignant ou un client. Quand on le voit tourner, on doit avoir l'impression
qu'un **analyste senior a travaillé une demi-journée**.

## Rejouer la démonstration

```bash
sudo -u postgres bash demo/setup_scenario.sh retail   # charge la base source
cd backend && python ../demo/verify.py retail          # Noreon rejoue et affiche
```

## Contenu du dossier

| Fichier | Rôle |
|---|---|
| `question.md` | La question et son cadrage métier |
| `notes.md` | **La vérité plantée** (ground truth) |
| `gold_standard.md` | Le rapport **idéal**, écrit à la main |
| `expected_reasoning.md` | Le raisonnement attendu, étape par étape |
| `expected_sql.sql` | Les requêtes clés (auditables) |
| `expected_charts.md` | Les graphiques attendus |
| `expected_report.md` | La structure du rapport exportable |
| `expected_decisions.md` | Les décisions attendues par rôle |
| `seed.sql` | La base source synthétique et déterministe |

## Comparaison Gold Standard ⇄ Noreon

Sortie **vérifiée** de `python demo/verify.py retail` (moteur hors-ligne, sans clé) :

- **Intention** : `diagnostic` → « Diagnostiquer une baisse de amount_ttc ». ✅
- **Chronologie** : « Après une stabilité jusqu'en 2024-11, le CA recule
  progressivement pendant 4 périodes consécutives. » ✅
- **Cause (attribution)** : **« la baisse est portée à 97 % par la région
  Provence-Alpes-Côte d'Azur ».** ✅ *(= Gold Standard)*
- **Changement d'avis** : « À première vue la structure du chiffre pointait la
  fidélité ; mais en isolant la variation, la baisse vient de PACA. » ✅
- **Decision Engine** : ★★★★★ Directeur réseau → audit PACA ; ★★★ Directeur
  financier → sécuriser la marge. ✅
- **Projection d'inaction** : « ~ −10 % supplémentaires sur 3 périodes si rien ne
  change — projection, pas prédiction. » ✅
- **Sérendipité** : signale spontanément des emails non conformes (qualité). ✅
- **Confiance** : 77 / 100. ✅

### Écart Gold ⇄ Noreon (la « liste de courses »)

| Élément du Gold Standard | Noreon | Écart |
|---|---|---|
| Cause = PACA (~ 97 % de la baisse) | ✅ 97 %, région en tête | **aucun** |
| Baisse depuis le pic | ✅ tendance + point bas | mineur (parle en % début→fin, pas pic→fin) |
| Décideur prioritaire = réseau (PACA) | ✅ ★★★★★ réseau | **aucun** |
| Nuance panier vs trafic | ⚠️ non explicité automatiquement | *piste #1* |
| Facteur produit (rupture High-Tech) | ⚠️ non attribué (vit sur `order_items`) | *piste #2* |

Ces deux écarts sont le **carburant du développement**, exactement comme prévu par
la méthode Gold Standard :

- **Piste #1 — panier vs trafic** : ajouter une décomposition
  *volume × panier* de la variation (« la baisse vient du panier, pas du trafic »).
- **Piste #2 — attribution multi-tables** : attribuer la variation à une dimension
  atteinte par 2 sauts de jointure (catégorie produit via `order_items`).

> Ce qui a **déjà** été livré grâce à ce scénario : l'**attribution de la
> variation** (ADR D-30). Avant, Noreon répondait « le plus gros segment pèse le
> plus » (tautologie) ; désormais il répond « la baisse vient de PACA à 97 % ».

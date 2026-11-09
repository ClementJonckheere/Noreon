# Gold Standard — Retail

> Le rapport **idéal**, écrit à la main : ce qu'un excellent analyste rendrait
> après une demi-journée de travail. C'est la **référence** contre laquelle on
> mesure Noreon (cf. `README.md` pour la comparaison Gold ⇄ Noreon).

---

## Réponse (niveau 1 — la décision)

**Le chiffre d'affaires recule de −12,8 % depuis son pic de février 2025, et la
quasi-totalité de cette baisse (~ 97 %) vient de la région Provence-Alpes-Côte
d'Azur (magasins de Marseille et Nice).** Ce n'est pas un problème de trafic —
les clients viennent toujours — mais de **panier moyen**, qui s'y effondre de
−23 %. En parallèle, la gamme High-Tech est en rupture depuis mars (quantités
divisées par deux), ce qui amplifie le recul.

**Action prioritaire :** audit terrain immédiat de Marseille et Nice (concurrence,
prix, exécution) ; sécuriser l'approvisionnement High-Tech.

---

## Diagnostic (niveau 2 — comprendre)

### 1. Ampleur et rythme
- CA stable puis croissant de janv. 2024 à **févr. 2025 (~ 41 600 €/mois)**.
- **Déclin sur 4 mois** (mars→juin 2025), **accéléré** : −7 %, puis −1 %, −2 %, −3 %
  d'un mois sur l'autre → **−12,8 % depuis le pic**.

### 2. D'où vient la baisse ? (attribution, pas structure)
Comparaison fenêtre récente (mars–juin) vs précédente (nov.–févr.), par région :

| Région                          | Δ CA/4 mois | Contribution à la baisse |
|---------------------------------|-------------|--------------------------|
| **Provence-Alpes-Côte d'Azur**  | **−14 000 €** | **~ 97 %**             |
| Hauts-de-France                 | −440 €      | ~ 3 %                    |
| Auvergne-Rhône-Alpes            | +920 €      | (compense)               |
| Île-de-France                   | +990 €      | (compense)               |

→ **Une seule région porte la baisse.** Les autres sont stables ou en hausse.

### 3. Trafic ou panier ? (écarter la fausse piste)
- Clients actifs au global : **stables** (290–313/mois) → ce n'est pas « moins de clients ».
- PACA : trafic 596 → 567 (**−5 %**) mais panier **86 € → 66 € (−23 %)**.
- → **C'est le panier qui s'effondre**, pas la fréquentation.

### 4. Facteur aggravant : rupture produit
- Quantités **High-Tech** : ~ 462/mois (janv.–févr.) → ~ 220/mois (dès mars) — **÷ 2**.
- Cohérent avec une rupture d'approvisionnement qui pénalise le panier.

---

## Preuves (niveau 3)
Chaque chiffre est adossé à une requête en lecture seule (cf. `expected_sql.sql`)
et à un graphique (cf. `expected_charts.md`). Réserves de confiance : ~ 2,5 %
d'emails invalides et quelques `store_id` orphelins (magasin 99) — sans effet sur
la conclusion (le signal PACA est massif), mais notés pour l'honnêteté.

---

## Recommandations par rôle (Decision Engine)

| Rôle                | Priorité | Recommandation | Impact estimé |
|---------------------|:--------:|----------------|---------------|
| **Directeur réseau**| ★★★★★ | Audit terrain Marseille + Nice : concurrence, prix, exécution. | Élevé — porte 97 % de la baisse |
| Directeur produit   | ★★★★☆ | Rétablir l'approvisionnement High-Tech ; plan anti-rupture. | Moyen |
| Directeur financier | ★★★☆☆ | Sécuriser la marge et la trésorerie le temps du redressement. | Moyen |

**Et si l'on ne fait rien ?** Si la tendance des 4 derniers mois se maintient et
qu'aucun changement majeur n'intervient, le CA pourrait reculer d'environ **10 %
supplémentaires** sur le trimestre à venir. *Projection sous hypothèses, pas une
prédiction.*

---

## Auto-critique (honnêteté intellectuelle)
- L'analyse suppose qu'aucune promotion ou événement exceptionnel n'a faussé la
  fenêtre récente.
- Le mois le plus récent peut être incomplet (données encore en cours de saisie).
- La cause « concurrent » est une **hypothèse métier** à valider sur le terrain :
  les données montrent *où* et *comment* (PACA, panier), pas *pourquoi* avec certitude.

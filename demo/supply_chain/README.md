# Scénario — Supply Chain

> **« Pourquoi les ruptures de stock augmentent-elles ? »** · distributeur fictif
> *LogiPro* · base `noreon_demo_supply_chain` · 100 % synthétique.

```bash
sudo -u postgres bash demo/setup_scenario.sh supply_chain
cd backend && python ../demo/verify.py supply_chain
```

## Comparaison Gold Standard ⇄ Noreon (sortie vérifiée)

- **Intention** : `diagnostic` → « Comprendre une hausse de cout_rupture ». ✅
- **Chronologie** : « progresse pendant 4 périodes consécutives (+115 %). » ✅
- **Cause (attribution)** : **« la hausse est portée à 97 % par Fournisseur Delta »**. ✅
- **Changement d'avis** : « la structure pointait la temporalité ; la hausse vient
  du Fournisseur Delta. » ✅
- **Decision Engine** : ★★★★★ Directeur supply chain → sécuriser Delta (sourcing
  alternatif, stock de sécurité, pénalités). ✅ *(rôle ajouté pour ce scénario)*
- **Confiance** : 77 / 100. ✅

### Écart Gold ⇄ Noreon
| Élément | Noreon | Écart |
|---|---|---|
| Cause = « Fournisseur Delta » (~ 97 %) | ✅ 97 % | **aucun** |
| Rôle supply chain dans les décisions | ✅ ajouté | **aucun** (livré ici) |
| Double effet nombre × durée | ⚠️ non décomposé | *piste : décomposer la mesure* |

Contenu : `question.md`, `notes.md` (vérité plantée), `gold_standard.md`, `seed.sql`.

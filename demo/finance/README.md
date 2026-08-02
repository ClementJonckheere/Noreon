# Scénario — Finance

> **« Pourquoi la marge diminue-t-elle ? »** · industriel fictif *Novindus* ·
> base `noreon_demo_finance` · 100 % synthétique.

```bash
sudo -u postgres bash demo/setup_scenario.sh finance
cd backend && python ../demo/verify.py finance
```

## Comparaison Gold Standard ⇄ Noreon (sortie vérifiée)

- **Intention** : `diagnostic` → « Diagnostiquer une baisse de montant_marge ». ✅
- **Chronologie** : « après une stabilité, recule pendant 4 périodes (−33 %). » ✅
- **Cause (attribution)** : **« la baisse est portée à 92 % par Composants »**. ✅
- **Changement d'avis** : « la structure pointait la temporalité ; la baisse vient
  de la ligne Composants. » ✅
- **Decision Engine** : ★★★★ Directeur produit → revoir la gamme Composants ;
  ★★★★ Directeur financier. ✅
- **Projection d'inaction** : « ~ −26 % supplémentaires si rien ne change. » ✅
- **Confiance** : 77 / 100. ✅

### Écart Gold ⇄ Noreon
| Élément | Noreon | Écart |
|---|---|---|
| Cause = ligne « Composants » (~ 92 %) | ✅ 92 % | **aucun** |
| Mécanique « c'est le coût, pas le CA » | ⚠️ non explicitée | *piste : décomposer marge = CA − coût* |

Contenu : `question.md`, `notes.md` (vérité plantée), `gold_standard.md`, `seed.sql`.

# Scénario — RH

> **« Pourquoi les départs augmentent-ils ? »** · ESN fictive *TalentForge* ·
> base `noreon_demo_hr` · 100 % synthétique.

```bash
sudo -u postgres bash demo/setup_scenario.sh hr
cd backend && python ../demo/verify.py hr
```

## Comparaison Gold Standard ⇄ Noreon (sortie vérifiée)

- **Intention** : `diagnostic` → « Comprendre une hausse de cout_remplacement ». ✅
- **Chronologie** : « après une stabilité, progresse pendant 4 périodes (+75 %). » ✅
- **Cause (attribution)** : **« la hausse est portée à 100 % par l'Ingénierie »**. ✅
- **Facteur secondaire** : motif « Démission » (~ 66 %) — cohérent avec le Gold Standard. ✅
- **Changement d'avis** : « la structure pointait la temporalité ; la hausse vient
  de l'Ingénierie. » ✅
- **Decision Engine** : ★★★★★ Directeur des ressources humaines → plan de rétention
  Ingénierie. ✅ *(rôle ajouté pour ce scénario)*
- **Sérendipité** : signale les emails non conformes. ✅
- **Confiance** : 77 / 100. ✅

### Écart Gold ⇄ Noreon
| Élément | Noreon | Écart |
|---|---|---|
| Cause = département « Ingénierie » (~ 100 %) | ✅ 100 % | **aucun** |
| Motif dominant = « Démission » | ✅ facteur secondaire | **aucun** |
| Rôle RH dans les décisions | ✅ ajouté | **aucun** (livré ici) |
| Mesure = coût de remplacement | ✅ après correction du piège « net » | **corrigé** |

Contenu : `question.md`, `notes.md` (vérité plantée), `gold_standard.md`, `seed.sql`.

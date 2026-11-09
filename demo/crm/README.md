# Scénario — CRM

> **« Pourquoi le churn augmente-t-il ? »** · SaaS fictif *FluxCRM* ·
> base `noreon_demo_crm` · 100 % synthétique.

```bash
sudo -u postgres bash demo/setup_scenario.sh crm
cd backend && python ../demo/verify.py crm
```

## Comparaison Gold Standard ⇄ Noreon (sortie vérifiée)

- **Intention** : `diagnostic` → « Comprendre une hausse de revenu_perdu ». ✅
- **Chronologie** : « progresse pendant 4 périodes consécutives, avec une
  accélération en 2025-06 (+64 %). » ✅
- **Cause (attribution)** : **« la hausse est portée à 100 % par la Publicité
  payante »**. ✅ *(= Gold Standard)*
- **Facteur secondaire** : plan « Basic » (90 %) — cohérent avec la nuance nombre/revenu. ✅
- **Changement d'avis** : « la structure pointait la temporalité ; la hausse vient
  du canal Publicité payante. » ✅
- **Decision Engine** : ★★★★★ Responsable des opérations → auditer le canal. ✅
- **Sérendipité** : signale les emails non conformes. ✅
- **Confiance** : 77 / 100. ✅

### Écart Gold ⇄ Noreon
| Élément | Noreon | Écart |
|---|---|---|
| Cause = canal « Publicité payante » | ✅ 100 % | **aucun** |
| Nuance nombre vs revenu | ⚠️ implicite (Basic en secondaire) | mineur |
| Projection « et si rien ne change » | ⚠️ absente (réservée aux baisses) | *piste : projeter aussi les hausses de métriques « mauvaises »* |

Contenu : `question.md`, `notes.md` (vérité plantée), `gold_standard.md`, `seed.sql`.

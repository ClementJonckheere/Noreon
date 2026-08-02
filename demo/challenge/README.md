# Noreon Challenge

> Des scénarios conçus pour **casser** le moteur. Le but n'est pas d'avoir 100 —
> le but, c'est que le moteur **apprenne**.

Contrairement aux 5 scénarios métier (une cause nette, vérifiable), les challenges
sont **adversariaux** : cause diffuse, causes multiples, données contradictoires,
saisonnalité + promotion, causalité inversée, qualité catastrophique, faux
positifs, colonnes opaques… Chaque challenge documente sa **difficulté**, la
**réponse idéale**, et — s'il reste — la **limite connue** du moteur.

```bash
sudo -u postgres bash demo/setup_scenario.sh challenge/<nom>
cd backend && python ../demo/benchmark.py --challenge     # verdict par challenge
cd backend && python ../demo/verify.py challenge/<nom>    # sortie détaillée
```

Le benchmark affiche `APPRIS ✅` quand le moteur gère le piège, `À CORRIGER ❌`
sinon (avec la limite). C'est le moteur de la boucle scientifique :

```
Challenge → Le moteur se trompe → On corrige → Le challenge passe → Nouveau challenge
```

## Challenges livrés

| Challenge | Piège | État |
|---|---|---|
| `cause_diffuse/` | Baisse **systémique** (aucun coupable localisé) — le moteur retombait sur une tautologie (« le plus gros segment »). | **APPRIS ✅** (lift ≥ 1.5 + « baisse généralisée », ADR D-33) |

## Prochains challenges (feuille de route)

- **Causes multiples** (40/35/25 %) : nommer les trois, pas une seule.
- **Deux causes simultanées** (fermeture magasin + changement de prix).
- **Saisonnalité + promotion** : distinguer l'effet calendaire de l'effet réel.
- **Colonnes opaques** (`t1`, `c3`…) : robustesse quand le nommage ne guide plus.
- **Causalité inversée** / faux positifs / qualité de données catastrophique.

> Chaque challenge résolu laisse derrière lui une **amélioration réelle du moteur**
> — pas une fonctionnalité ajoutée « au cas où », mais une correction dictée par un
> échec mesuré.

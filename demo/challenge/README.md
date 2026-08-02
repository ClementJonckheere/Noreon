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
| `colonnes_opaques_n1/` | **Toutes les colonnes opaques** (`col_003`, `a3`…) — le moteur ne peut plus lire les noms. | **APPRIS ✅** (mesure + identifiant détectés PAR LES DONNÉES ; cause trouvée par la VALEUR, ADR D-34) |

> **Colonnes opaques — la preuve la plus forte.** Même scénario que retail (PACA
> 97 %), tous les noms rendus opaques. Noreon retrouve la mesure (`col_003`) par son
> profil et la cause (« Provence-Alpes-Côte d'Azur ») par la valeur du segment — il
> comprend donc les **données**, pas seulement le schéma. Limite restante : le
> routage vers un rôle métier dépend encore du nom de l'axe.

## Prochains challenges (feuille de route)

- **Colonnes opaques N2** : FK **non déclarées** → inférer la relation par
  recouvrement de valeurs (la vraie robustesse « données, pas schéma »).
- **Colonnes opaques N3** : valeurs bruitées + synonymes métier (client → adhérent).
- **Causes multiples** (40/35/25 %) : nommer les trois, pas une seule.
- **Deux causes simultanées** (fermeture magasin + changement de prix).
- **Saisonnalité + promotion** : « la baisse dépasse la saisonnalité habituelle ».
- **Qualité catastrophique** : savoir dire « je ne peux pas conclure ».
- **Causalité inversée** (promotions ↑ *parce que* ventes ↓) — à garder pour plus tard.

> Chaque challenge résolu laisse derrière lui une **amélioration réelle du moteur**
> — pas une fonctionnalité ajoutée « au cas où », mais une correction dictée par un
> échec mesuré.

# Challenge « Saisonnalité » — la vérité

## Le piège
La question « pourquoi le CA baisse depuis 4 mois ? » suppose un problème. Mais la
baisse observée (printemps → été) est un **creux estival** qui revient **chaque
année**, dans les mêmes proportions. 30 mois d'historique (janv. 2023 → juin 2025),
+3 %/an de croissance régulière.

- Comparé au **mois précédent** : « ça baisse ! » (−19 % de mars à juin).
- Comparé à la **même période l'an dernier** : **+4 %** — c'est même un peu mieux.

## La bonne réponse
> « Cette baisse est **SAISONNIÈRE** : juin est toujours plus faible. En glissement
> annuel, le CA est comparable (voire au-dessus) à l'an dernier. **Pas d'anomalie,
> aucune action corrective** — surveiller que la reprise post-été a bien lieu. »

Beaucoup d'analystes (et de moteurs) oublient la saisonnalité et déclenchent une
fausse alerte. Le bon comportement est de **ne rien faire** — et de le dire.

## Ce que le challenge a appris au moteur (ADR D-38)
Avant de chercher une cause, le moteur teste la **saisonnalité** (dès ~ 16 mois
d'historique) : il compare la fenêtre récente à la **même période l'an dernier**
(glissement annuel), pas à la période précédente. Si le niveau récent n'est pas
pire que l'an dernier (≥ −4 %), la baisse est déclarée **saisonnière** :
- l'attribution de cause est **sautée** (il n'y a rien à isoler) ;
- **aucune décision corrective** n'est produite ;
- la recommandation invite à suivre l'indicateur **en glissement annuel**.

## Résultat vérifié
```
· baisse reconnue saisonnière : ✓
· aucune action corrective : ✓
Noreon dit : la baisse récente est SAISONNIÈRE ; +4 % en glissement annuel — pas une anomalie.
```

Valide la propriété **P-07** (saisonnalité) — cf. `demo/PROPERTIES.md`.

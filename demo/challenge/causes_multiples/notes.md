# Challenge « Causes multiples » — la vérité

## Le piège
La baisse du CA ne vient **pas d'une cause unique**. Elle se répartit sur **trois
magasins**, situés dans **trois régions différentes** (pour qu'aucun regroupement
géographique ne reconcentre la cause en une seule) :

| Foyer | Région | Contribution à la baisse |
|---|---|---|
| Marseille | Provence-Alpes-Côte d'Azur | ~ 40–44 % |
| Lyon | Auvergne-Rhône-Alpes | ~ 32–35 % |
| Lille | Hauts-de-France | ~ 20–25 % |

Les trois autres magasins (Paris ×2, Nice) sont stables.

## La bonne réponse
> « **Trois foyers** expliquent la baisse : Marseille (~40 %), Lyon (~35 %),
> Lille (~25 %). Il faut agir sur les trois — un plan pour un seul ne redressera
> qu'une fraction. »

Un mauvais moteur répond « la cause est X » (une seule). Un moteur trop prudent
répond « baisse généralisée » (alors qu'elle est concentrée sur 3 foyers, pas
diffuse). Le bon moteur **nomme les trois**.

## Ce que le challenge a appris au moteur (ADR D-36)
L'attribution ne prend plus seulement le **premier** segment de chaque axe : elle
calcule la contribution et le **lift** de **chaque** segment, puis classe l'axe en :
- **cause unique** — un segment ≥ 55 % (lift franc) ;
- **causes multiples** — plusieurs foyers concentrés (≥ 15 % chacun, lift ≥ 1,3)
  expliquant ensemble ≥ 60 % ;
- **généralisée** — aucun foyer disproportionné (P-03).

Rasoir d'Occam au moment de choisir l'axe : « une région à 97 % » l'emporte sur
« deux villes à 51/46 % » (même fait, explication plus simple).

## Résultat vérifié
```
· foyers nommés : ✓ [PACA (44%), ARA (32%), HdF (20%)] (cumul 96%)
Noreon dit : la baisse ne vient pas d'une cause unique mais de 3 foyers — …
```

Valide la propriété **P-06** (multi-causes) — cf. `demo/PROPERTIES.md`.

> Note : le moteur regroupe par **région** (une ville déclinante par région) plutôt
> que par ville — équivalent ici (Nice, l'autre ville de PACA, est stable), et plus
> concentré au sens d'Occam.

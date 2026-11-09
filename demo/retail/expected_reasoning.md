# Raisonnement attendu — Retail

Étapes que le moteur d'investigation doit enchaîner (Question → Plan →
Sous-questions → Synthèse). C'est la trace « vivante » attendue.

1. **Comprendre l'intention.** Question diagnostique → intention `diagnostic`,
   reformulée « Diagnostiquer une baisse de {mesure} ».
2. **Choisir le sujet et la mesure.** Sujet = `orders` (table de faits, « ventes /
   CA »). Mesure = `sum(amount_ttc)` (TTC — piège sémantique à ne pas confondre
   avec `net_price` HT).
3. **Tendance dans le temps.** Agréger le CA par mois. Constat : pic févr. 2025,
   puis baisse 4 périodes consécutives, **accélérée**.
4. **Attribution de la variation** *(l'étape décisive)*. Comparer la fenêtre
   récente (mars–juin) à la précédente (nov.–févr.), **axe par axe**, et classer
   par **contribution à la baisse** (pas part du total). → Région PACA ~ 97 %.
5. **Écarter la fausse piste « trafic ».** Vérifier que le nombre de clients
   actifs est stable → la baisse vient du **panier**, pas de la fréquentation.
6. **Changement d'avis (auto-révision).** L'hypothèse de départ (structure du
   chiffre : fidélité / plus gros segment) est **corrigée** : la baisse vient de
   la région PACA.
7. **Synthèse.** Conclusion adossée à l'attribution ; recommandations priorisées
   par rôle ; projection prudente de l'inaction ; auto-critique.

## Principe directeur

> « D'où vient la **baisse** ? » ≠ « D'où vient le **chiffre** ? »
> Le second mène à la tautologie (« le plus gros segment pèse le plus »). Le
> premier isole la cause réelle : c'est la **contribution à la variation**.

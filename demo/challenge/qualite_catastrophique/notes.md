# Challenge « Qualité catastrophique » — la vérité

## Le piège
Les données sont **trop mauvaises pour conclure** :
- ~ 45–55 % des montants (`amount_ttc`) sont NULL, ou des sentinelles `0` / `-1`
  (« inconnu ») ;
- ~ 50 % des dates (`order_date`) sont NULL → **aucune tendance fiable** ;
- ~ 60 % des `store_id` sont NULL ou orphelins → **aucune ventilation fiable**.

## La bonne réponse
> « **Je ne peux pas conclure avec suffisamment de confiance** : la qualité des
> données est insuffisante (montants et dates majoritairement manquants). Toute
> tendance ou cause serait trompeuse. Priorité : fiabiliser la saisie avant
> d'analyser. »

C'est un **signe de maturité**. Un mauvais moteur invente une réponse à partir des
45 % de données exploitables et se trompe. Le bon moteur **s'abstient honnêtement**
— et le dit clairement.

## Ce que le challenge a appris au moteur (ADR D-39)
Avant de chercher une tendance ou une cause, le moteur **contrôle la fiabilité** :
il lit le taux de valeurs manquantes (profilage) de la **mesure** et de la **date**.
Au-delà de 40 %, il **s'abstient** :
- l'investigation s'arrête sur un constat de fiabilité ;
- la conclusion est « je ne peux pas conclure… » (avec les taux exacts) ;
- **aucune décision** n'est produite ;
- la recommandation invite à **fiabiliser la saisie** avant d'analyser.

## Résultat vérifié
```
· abstention honnête : ✓ (« je ne peux pas conclure… amount_ttc 45 %, order_date 50 % »)
· aucune décision : ✓
```

Valide la propriété **P-08** (humilité) — cf. `demo/PROPERTIES.md`.

"""Phase 2 — C6 : CapabilityResolver.

Couche DOMAIN-AGNOSTIC entre `interpretation_json` (intention, sortie LLM) et le
PlanCompiler (exécution). Elle traduit l'intention en EXIGENCES analytiques/
exécutables résolues contre concepts/entités/mesures/relations VALIDÉES, qualité
et permissions — et produit le `resolved_plan_json` (contrat C1).

`goal_type ≠ capability`. Le grain et le fanout sont des primitives de 1er ordre :
une jointure valide n'est pas une agrégation sûre. Rien n'est jamais inventé.
"""

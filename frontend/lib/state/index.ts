// Machine à états de Noreon — point d'entrée unique.
// Aucun composant ne fait transiter un état hors de ce module ; il consomme
// transitions (local) et propagations (E1..E4), et affiche les verdicts des gardes.
export * from "./types";
export * from "./guards";
export * from "./transitions";
export * from "./propagations";

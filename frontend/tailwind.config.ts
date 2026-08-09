import type { Config } from "tailwindcss";

// =============================================================================
// Noreon — Design System v1.0 « Precision editorial interface »
//
// Un outil rigoureux, presque scientifique, dont les réponses se lisent comme un
// rapport d'analyste. 70 % instrument de précision, 30 % document éditorial.
//
// Règle d'or : aucun composant n'écrit une couleur en dur. Tout passe par ces
// jetons — seule condition pour que le mode sombre arrive plus tard sans reprise.
// =============================================================================

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // -- Surfaces (papier chaud, pas gris froid) --------------------------
        paper: "#FCFBF9", // background-primary — zone de lecture
        "paper-2": "#F5F4F1", // background-secondary — sidebar, panneaux, entêtes
        raised: "#FFFFFF", // surface-raised — cartes sémantiques, modales

        // -- Encre & texte ----------------------------------------------------
        ink: "#101820", // text-primary — conclusions, chiffres, titres
        "ink-2": "#4A5560", // text-secondary — corps de texte long
        "ink-3": "#646E79", // text-tertiary — étiquettes mono, métadonnées

        // -- Bordures ---------------------------------------------------------
        "line-subtle": "#E8E6E1", // séparateurs de lignes en zone dense
        line: "#DBD8D2", // contour des cartes, champs, boutons secondaires
        "line-strong": "#C4C0B8", // focus, sélection de ligne
        grid: "#F0EFEB", // grille de graphique (horizontale seule)

        disabled: "#A9AFB6", // texte d'un bouton inactif — jamais du bleu pâli

        // -- Bleu Noreon · l'utilisateur & le produit -------------------------
        // Navigation, action primaire, sélection, lien. « Vous pouvez agir. »
        brand: {
          50: "#F4F8FF",
          100: "#E7F0FF", // fonds de sélection
          200: "#C9DDFF", // anneau de focus / séries de graphique
          300: "#9EC3FF",
          400: "#67A0F5",
          500: "#357FEA",
          600: "#1769E0", // MARQUE — action primaire, nav active
          700: "#1458BE", // survol
          800: "#164B98",
          900: "#173F78",
          DEFAULT: "#1769E0",
        },

        // -- Violet · le raisonnement de la machine ---------------------------
        // Investigation, hypothèse, découverte, recalcul, confiance de Noreon.
        reason: {
          DEFAULT: "#5B4BD6",
          hover: "#4A3BC0",
          subtle: "#EEEBFC",
        },

        // -- Vert · validation externe (jamais la confiance de Noreon) --------
        success: {
          DEFAULT: "#1F8A5F",
          hover: "#166B49",
          subtle: "#E2F3EB",
        },

        // -- Orange · limite épistémique (« j'ai travaillé, je ne conclus pas »)
        warning: {
          DEFAULT: "#C77A13",
          hover: "#8F5609",
          subtle: "#FBF0DE",
        },

        // -- Rouge · blocage (« je ne peux pas travailler ») ------------------
        blocker: {
          DEFAULT: "#C0392B",
          hover: "#A32C1F",
          subtle: "#FAE7E4",
        },

        // -- Alias de compatibilité (anciens jetons → nouvelle palette) -------
        // Permet aux écrans non encore repris d'hériter du papier chaud et du
        // bleu Noreon sans réécriture. À retirer une fois tout migré.
        noreon: {
          bg: "#FCFBF9",
          panel: "#FFFFFF",
          border: "#DBD8D2",
          accent: "#1769E0",
          soft: "#646E79",
        },
      },

      fontFamily: {
        // Instrument Sans pour tout ce qui se lit ; JetBrains Mono pour tout ce
        // qui se vérifie (85 / 15 %). Le mono ne sert jamais de style.
        sans: ["var(--font-sans)", "Instrument Sans", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "ui-monospace", "monospace"],
      },

      fontSize: {
        // display / title / heading / subhead / body / small — échelle éditoriale
        display: ["2rem", { lineHeight: "1.15", letterSpacing: "-0.025em", fontWeight: "600" }],
        title: ["1.5rem", { lineHeight: "1.2", letterSpacing: "-0.02em", fontWeight: "600" }],
        heading: ["1.1875rem", { lineHeight: "1.3", letterSpacing: "-0.015em", fontWeight: "600" }],
        subhead: ["0.96875rem", { lineHeight: "1.4", letterSpacing: "-0.01em", fontWeight: "500" }],
        body: ["0.84375rem", { lineHeight: "1.6" }], // 13.5px
        small: ["0.75rem", { lineHeight: "1.5" }], // 12px
        metric: ["0.9375rem", { lineHeight: "1.2", fontWeight: "500" }], // 15px mono
        label: ["0.625rem", { lineHeight: "1.4", letterSpacing: "0.1em", fontWeight: "500" }], // 10px caps
      },

      borderRadius: {
        // Trois rayons seulement.
        field: "4px",
        button: "7px",
        card: "10px",
      },

      boxShadow: {
        // Trois élévations dont la première est plate ; l'ombre reste l'exception.
        e1: "0 1px 2px rgba(16,24,32,0.06)", // carte
        e2: "0 8px 28px rgba(16,24,32,0.14)", // flottant (modale, tiroir, palette)
        card: "0 1px 2px rgba(16,24,32,0.06)", // alias compat
      },

      spacing: {
        // Base de 4 px — échelle officielle (les valeurs Tailwind couvrent le reste).
        "18": "4.5rem",
      },

      ringColor: {
        focus: "#C9DDFF",
      },
      ringWidth: {
        focus: "3px",
      },

      keyframes: {
        "noreon-fadein": {
          from: { opacity: "0", transform: "translateY(3px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "noreon-pulse": {
          "0%, 80%, 100%": { opacity: "0.3" },
          "40%": { opacity: "1" },
        },
      },
      animation: {
        // Transitions 120–200 ms, en sortie.
        "fade-in": "noreon-fadein 160ms ease-out",
      },
    },
  },
  plugins: [],
};

export default config;

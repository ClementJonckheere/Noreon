import type { Config } from "tailwindcss";

// =============================================================================
// Noreon — Design System v1.0 « Precision editorial » (handoff design).
//
// Les couleurs pointent vers les variables de globals.css (jetons) : le mode
// sombre se fera plus tard en redéfinissant :root, sans toucher aux composants.
// Aucun composant n'écrit une couleur en dur.
//
// Noms canoniques du handoff (bg-primary, ink-secondary, reasoning, success…).
// Un petit bloc d'alias en fin conserve les écrans pas encore migrés.
// =============================================================================

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: "var(--background-primary)",
          secondary: "var(--background-secondary)",
        },
        surface: { raised: "var(--surface-raised)" },
        ink: {
          DEFAULT: "var(--text-primary)", // compat : text-ink / bg-ink
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          tertiary: "var(--text-tertiary)",
          disabled: "var(--text-disabled)",
          "2": "var(--text-secondary)", // compat : text-ink-2
          "3": "var(--text-tertiary)", // compat : text-ink-3
        },
        line: {
          subtle: "var(--border-subtle)",
          DEFAULT: "var(--border-default)",
          strong: "var(--border-strong)",
          inset: "var(--divider-inset)",
        },
        brand: {
          50: "var(--blue-50)", 100: "var(--blue-100)", 200: "var(--blue-200)",
          300: "var(--blue-300)", 400: "var(--blue-400)", 500: "var(--blue-500)",
          600: "var(--blue-600)", 700: "var(--blue-700)", 800: "var(--blue-800)",
          900: "var(--blue-900)",
          DEFAULT: "var(--accent-brand)",
          subtle: "var(--accent-brand-subtle)",
          hover: "var(--accent-brand-hover)",
        },
        reasoning: {
          DEFAULT: "var(--accent-reasoning)",
          subtle: "var(--accent-reasoning-subtle)",
          hover: "var(--accent-reasoning-hover)",
        },
        success: {
          DEFAULT: "var(--status-success)",
          subtle: "var(--status-success-subtle)",
          hover: "var(--status-success-hover)",
          border: "var(--status-success-border)",
          bg: "var(--status-success-bg)",
        },
        warning: {
          DEFAULT: "var(--status-warning)",
          subtle: "var(--status-warning-subtle)",
          hover: "var(--status-warning-hover)",
          border: "var(--status-warning-border)",
          bg: "var(--status-warning-bg)",
        },
        blocker: {
          DEFAULT: "var(--status-blocker)",
          subtle: "var(--status-blocker-subtle)",
          hover: "var(--status-blocker-hover)",
          border: "var(--status-blocker-border)",
          bg: "var(--status-blocker-bg)",
        },

        // -- Alias de compatibilité (écrans pas encore migrés) ----------------
        // Même variables : « paper/ink/reason/noreon.* » restent valides le
        // temps de reprendre chaque écran. À retirer en fin de migration.
        paper: "var(--background-primary)",
        "paper-2": "var(--background-secondary)",
        raised: "var(--surface-raised)",
        grid: "var(--divider-inset)",
        reason: {
          DEFAULT: "var(--accent-reasoning)",
          subtle: "var(--accent-reasoning-subtle)",
          hover: "var(--accent-reasoning-hover)",
        },
        disabled: "var(--text-disabled)",
        noreon: {
          bg: "var(--background-primary)",
          panel: "var(--surface-raised)",
          border: "var(--border-default)",
          accent: "var(--accent-brand)",
          soft: "var(--text-tertiary)",
        },
      },

      fontFamily: {
        // Auto-hébergées via next/font (variables --font-sans / --font-mono).
        sans: ["var(--font-sans)", "Instrument Sans", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "ui-monospace", "monospace"],
      },

      fontSize: {
        label: ["10px", { lineHeight: "1", letterSpacing: "0.1em", fontWeight: "500" }],
        small: ["12px", { lineHeight: "1.5" }],
        body: ["13.5px", { lineHeight: "1.6" }],
        metric: ["15px", { lineHeight: "1", fontWeight: "500" }],
        subhead: ["15.5px", { lineHeight: "1.4", letterSpacing: "-0.01em", fontWeight: "500" }],
        heading: ["19px", { lineHeight: "1.3", letterSpacing: "-0.015em", fontWeight: "600" }],
        title: ["24px", { lineHeight: "1.2", letterSpacing: "-0.02em", fontWeight: "600" }],
        display: ["32px", { lineHeight: "1.15", letterSpacing: "-0.025em", fontWeight: "600" }],
      },

      borderRadius: {
        field: "var(--radius-field)",
        button: "var(--radius-button)",
        card: "var(--radius-card)",
      },

      boxShadow: {
        card: "var(--elevation-1)",
        floating: "var(--elevation-2)",
        e1: "var(--elevation-1)", // alias compat
        e2: "var(--elevation-2)", // alias compat
        "focus-brand": "0 0 0 3px var(--blue-200)",
        "focus-field": "0 0 0 3px var(--blue-100)",
      },

      maxWidth: {
        reading: "640px", // corps de texte long
      },

      keyframes: {
        "noreon-fadein": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "noreon-pulse": {
          "0%, 80%, 100%": { opacity: "0.3" },
          "40%": { opacity: "1" },
        },
      },
      animation: {
        "fade-in": "noreon-fadein 220ms ease-out",
      },
    },
  },
  plugins: [],
};

export default config;

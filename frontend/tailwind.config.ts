import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Palette claire « argentée », à l'image du logo Noreon.
        noreon: {
          bg: "#eef1f6", // fond général (gris argenté très clair)
          panel: "#ffffff", // cartes / surfaces
          border: "#dce1ea", // bordures discrètes
          accent: "#3b6fd4", // bleu acier (lisible sur blanc)
          soft: "#5b6a82", // texte secondaire
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(15,23,42,0.04), 0 1px 3px rgba(15,23,42,0.06)",
      },
    },
  },
  plugins: [],
};

export default config;

import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        noreon: {
          bg: "#0b1020",
          panel: "#141b2e",
          border: "#25304a",
          accent: "#4f8cff",
          soft: "#9fb3d1",
        },
      },
    },
  },
  plugins: [],
};

export default config;

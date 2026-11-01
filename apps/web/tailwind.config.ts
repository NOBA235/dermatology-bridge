import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "var(--font-sans)",
          "Plus Jakarta Sans",
          "system-ui",
          "-apple-system",
          "sans-serif",
        ],
        mono: [
          "var(--font-mono)",
          "IBM Plex Mono",
          "ui-monospace",
          "SFMono-Regular",
          "monospace",
        ],
      },
      colors: {
        dermnet: {
          masthead: "#006599",
          subnav: "#127eb8",
          navy: "#0b2c44",
          navyHover: "#071f31",
          link: "#0072ab",
          surface: "#f4f8fb",
        },
        surface: {
          canvas: "#f4f8fb",
          card: "#ffffff",
          subtle: "#edf4f9",
          border: "#cbdce9",
        },
        ink: {
          primary: "#0f1e2e",
          secondary: "#334e68",
          muted: "#627d98",
        },
        clinical: {
          accent: "#006599",
          hover: "#004e78",
          improving: "#1f6f52",
          stalled: "#486581",
          worsening: "#b83b2b",
          hypothesis: "#006599",
          correlation: "#8a5a14",
        },
      },
      boxShadow: {
        clinical:
          "0 1px 3px 0 rgba(11, 44, 68, 0.06), 0 1px 2px -1px rgba(11, 44, 68, 0.04)",
        "clinical-md":
          "0 6px 16px -3px rgba(11, 44, 68, 0.09), 0 2px 6px -2px rgba(11, 44, 68, 0.05)",
      },
    },
  },
  plugins: [],
};

export default config;

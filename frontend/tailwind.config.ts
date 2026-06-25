import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: "#1a3a6b",
        "navy-dark": "#122850",
        sidebar: "#ffffff",
        "sidebar-hover": "#f0f4ff",
        "sidebar-active": "#e8eeff",
      },
    },
  },
  plugins: [],
};

export default config;

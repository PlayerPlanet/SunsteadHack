import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#0f0f0f",
        card: "#161616",
        border: "#262626",
      },
    },
  },
  plugins: [],
};

export default config;

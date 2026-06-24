import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./hooks/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17202a",
        line: "#d6dde5",
        panel: "#ffffff",
        mist: "#f4f7fa",
        brand: "#176b87",
        signal: "#d94f30"
      },
      boxShadow: {
        surface: "0 1px 2px rgba(23, 32, 42, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;

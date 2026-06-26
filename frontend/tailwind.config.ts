import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./hooks/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Neutral, professional SaaS palette.
        ink: "#0f172a", // primary text (slate-900)
        line: "#e2e8f0", // borders (slate-200)
        panel: "#ffffff", // card / surface
        mist: "#f8fafc", // app background / subtle fills (slate-50)
        // Brand: refined indigo with a darker hover and soft tint.
        brand: {
          DEFAULT: "#4f46e5",
          dark: "#4338ca",
          soft: "#eef2ff",
          ink: "#3730a3"
        },
        signal: "#e11d48"
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"]
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.125rem"
      },
      boxShadow: {
        surface: "0 1px 2px rgba(15, 23, 42, 0.06)",
        card: "0 1px 3px rgba(15, 23, 42, 0.08), 0 1px 2px rgba(15, 23, 42, 0.04)",
        lifted: "0 10px 30px -12px rgba(15, 23, 42, 0.25)"
      }
    }
  },
  plugins: []
};

export default config;

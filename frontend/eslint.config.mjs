import nextVitals from "eslint-config-next/core-web-vitals";

const config = [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"]
  },
  ...nextVitals.map((config) => ({
    ...config,
    rules: {
      ...config.rules,
      "react-hooks/set-state-in-effect": "off"
    }
  }))
];

export default config;

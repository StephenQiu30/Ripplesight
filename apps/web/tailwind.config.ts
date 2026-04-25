import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Avenir Next"', '"DIN Alternate"', '"Segoe UI"', "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;

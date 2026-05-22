import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a0a0f",
        bgsoft: "#11111a",
        ink: "#e8e8f0",
        muted: "#8a8a9c",
        gold: "#e7c87a",
        teal: "#6ee0c4",
        violet: "#a18cd1",
      },
      fontFamily: {
        sans: ["Inter Tight", "ui-sans-serif", "system-ui"],
        mono: ["Geist Mono", "ui-monospace", "monospace"],
      },
      backdropBlur: { xs: "2px" },
      animation: {
        breathe: "breathe 4s ease-in-out infinite",
        ripple: "ripple 1.4s ease-out infinite",
      },
      keyframes: {
        breathe: {
          "0%,100%": { transform: "scale(1)", opacity: "0.9" },
          "50%": { transform: "scale(1.04)", opacity: "1" },
        },
        ripple: {
          "0%": { transform: "scale(1)", opacity: "0.5" },
          "100%": { transform: "scale(1.5)", opacity: "0" },
        },
      },
    },
  },
  plugins: [],
} satisfies Config;

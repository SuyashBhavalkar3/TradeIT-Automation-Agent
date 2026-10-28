/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0b0e14",
        card: "#121721",
        cardBorder: "#1f2937",
        profit: "#10b981",
        loss: "#ef4444",
        warning: "#f59e0b",
        accent: "#3b82f6",
        armed: "#8b5cf6"
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Menlo", "Courier New", "monospace"],
      }
    },
  },
  plugins: [],
};


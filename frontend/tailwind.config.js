/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b1220",
        panel: "#111a2e",
        panel2: "#16223a",
        border: "#233252",
        accent: "#38bdf8",
        alert: "#f87171",
        warn: "#fbbf24",
        good: "#34d399",
      },
    },
  },
  plugins: [],
};

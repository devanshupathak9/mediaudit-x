/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#0b1220",
          900: "#0f172a",
          800: "#152036",
          700: "#1e293b",
        },
      },
      boxShadow: {
        card: "0 1px 2px 0 rgba(15,23,42,0.06), 0 1px 3px 0 rgba(15,23,42,0.06)",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.97)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
      },
      animation: {
        "fade-in": "fadeIn 0.25s ease-out both",
        "slide-up": "slideUp 0.3s ease-out both",
        "scale-in": "scaleIn 0.18s ease-out both",
      },
    },
  },
  plugins: [],
};

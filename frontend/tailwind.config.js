/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // KNOT6 visual identity, corrected pass: dark graphite/charcoal
        // foundation + forest green identity + signature orange used
        // sparingly. The earlier all-the-way-to-light-off-white pass
        // washed the app out and made the graph unreadable -- this
        // restores a dark ground while KEEPING the earlier pass's real
        // wins (the token-cascade architecture itself, the simplified
        // Overview information architecture, the earth-tone/state-based
        // graph coloring instead of rainbow). Redefined in place (same
        // token names every page already uses) so the whole app re-themes
        // from one source -- see docs/KNOT6_ARCHITECTURE.md's frontend
        // section for the token-cascade pattern this relies on.
        ink: "#0B0F0D",         // page background
        ink2: "#111815",        // secondary surface (sidebar, panels-on-ink)
        panel: "#111815",       // card surface
        panel2: "#151E1A",      // inset surface (inputs, table stripes)
        border: "#29352F",
        borderStrong: "#37453D",
        // `accent` is the pervasive one (active nav, links, focus rings,
        // primary buttons, badges -- 15+ files), so it has to stay legible
        // as small TEXT on a near-black background -- the brief's own
        // "Forest #24483D" / "Deep Forest #19352D" swatches are correct
        // for surfaces and fills but too dark to read as body-sized link
        // text at that size; a brighter sage-forest fills the same role
        // Forest/Deep Forest fill for surfaces (accentDim/accent2 below).
        // `signal`/`signalSoft` are the true, narrow accent -- graph
        // selection/importance emphasis only, exactly per the brief.
        accent: "#6FA98C",       // legible sage-forest -- links, focus, primary buttons
        accentDim: "#24483D",    // Forest -- secondary fills/badges
        accent2: "#19352D",      // Deep Forest -- darkest surface-level forest accent
        ink3: "#F1F0E9",         // primary text
        alert: "#E5645A",
        warn: "#D59A3A",
        good: "#4CA97F",
        muted: "#A7B0AA",        // secondary text
        signal: "#E06B3C",       // Signature Accent -- true accent, spent narrowly
        signalSoft: "#C98267",   // Soft Accent
        // Every page also reaches for Tailwind's built-in `slate-*` scale
        // directly (text-slate-100/200/300/400/500..., dozens of call
        // sites), assuming low numbers = brightest/most-prominent text on
        // a dark surface -- restored here to a real light-on-dark ramp
        // (undoing the previous pass's inversion), recalibrated to warm
        // forest-grays rather than the original cool blue-grays.
        slate: {
          50: "#F1F0E9",
          100: "#F1F0E9",
          200: "#D9D8CF",
          300: "#C3C2B8",
          400: "#A7B0AA",
          500: "#8B948C",
          600: "#707B74",
          700: "#545E57",
          800: "#37403A",
          900: "#29352F",
          950: "#151E1A",
        },
      },
      fontFamily: {
        // Source Serif 4 for headings/display text -- the single highest-
        // leverage move toward an editorial, analytical feel (matches the
        // KNOT6 dashboard reference's own serif headline treatment) without
        // touching body/mono, which stay exactly as legible as today.
        display: ["'Source Serif 4'", "ui-serif", "Georgia", "serif"],
        body: ["'Inter'", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "monospace"],
      },
      boxShadow: {
        // Calm elevation via real depth (black-based shadow, not a
        // colored glow) -- reads correctly on a dark ground, unlike a
        // light-mode-tuned tinted shadow.
        soft: "0 1px 2px rgba(0,0,0,0.35), 0 12px 28px -8px rgba(0,0,0,0.5)",
      },
    },
  },
  plugins: [],
};

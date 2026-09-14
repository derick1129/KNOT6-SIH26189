import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // react-force-graph-3d and @react-three/fiber/drei/postprocessing each
    // depend on "three" independently; without forcing a single physical
    // instance, Vite's dep pre-bundling can resolve two separate copies,
    // which breaks `instanceof`-based checks deep inside three's renderer
    // (surfaces as "object.intersectsFrustum is not a function").
    dedupe: ["three"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});

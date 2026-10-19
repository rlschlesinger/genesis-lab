// Vite builds and serves the browser lab; Vitest (configured below) tests it.
//
// In development the lab runs on Vite's server (http://127.0.0.1:5173) and every /api request,
// including the WebSocket stream, is forwarded to the Python API (`uv run genesis serve`,
// http://127.0.0.1:8765). The browser then sees one origin, so no cross-origin setup is needed.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const API = "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: API, ws: true } },
  },
  build: { outDir: "dist", sourcemap: true },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});

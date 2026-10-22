import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The API runs on its own (server/dev.sh run); the dev server passes /api to it, so the page and
// the API share one origin and the session cookie just works.
const api = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    host: "127.0.0.1",
    port: Number(process.env.PORT ?? 5173),
    strictPort: true,
    proxy: { "/api": { target: api } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    css: false,
  },
});

import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Vite dev server proxies /api and /health to the FastAPI backend
// so the frontend can use same-origin URLs in production too.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/schemas": "http://127.0.0.1:8000",
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/setupTests.ts"],
    css: false,
    // each test resets jsdom — fresh DOM per test
    isolate: true,
  },
});

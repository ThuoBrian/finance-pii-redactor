/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The build lands inside the Python package, which serves it. That folder is
// committed so end users never need Node (see CONTRIBUTING.md).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../finance_redactor/presentation/static",
    emptyOutDir: true,
    // No source maps in the shipped bundle: smaller download, nothing extra.
    sourcemap: false,
  },
  server: {
    port: 5173,
    strictPort: true,
    // The logo lives in the repo's assets/ folder, outside frontend/.
    fs: { allow: [".."] },
    // `just run` serves the API on 8501; changeOrigin sends Host 127.0.0.1:8501,
    // which the API's host check accepts.
    proxy: { "/api": { target: "http://127.0.0.1:8501", changeOrigin: true } },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // CSS stays unprocessed, except the tokens file the contrast test reads.
    css: { include: [/src\/index\.css/] },
  },
});

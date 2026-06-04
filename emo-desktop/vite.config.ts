import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  root: "ui",
  build: {
    outDir: "../dist",
    sourcemap: false,
    minify: "esbuild",
    target: "es2022",
  },
  server: {
    port: 5173,
  },
});

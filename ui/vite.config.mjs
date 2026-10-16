import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const uiRoot = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  root: uiRoot,
  build: {
    outDir: "dist/client",
  },
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    host: "127.0.0.1",
    hmr: false,
    allowedHosts: ["terminal.local"],
    fs: { strict: true, allow: [uiRoot] },
    warmup: {
      clientFiles: ["./src/main.jsx"],
    },
  },
  preview: { host: "127.0.0.1", allowedHosts: ["terminal.local"] },
  plugins: [react()],
});

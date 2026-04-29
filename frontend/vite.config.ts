import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import fs from "node:fs";

const DAEMON_URL = "http://127.0.0.1:5757";
const PROXIED_PREFIXES = [
  "/projects", "/sessions", "/snapshots", "/pages", "/trash",
  "/lint", "/ontology", "/activity", "/vault", "/lost-sessions",
  "/jobs", "/dead-letter", "/metrics", "/health", "/version",
  "/alerts", "/settings",
];

/** Restore .gitkeep after emptyOutDir wipes it so the dir stays tracked. */
function restoreGitkeep(): import("vite").Plugin {
  return {
    name: "restore-gitkeep",
    closeBundle() {
      const gitkeep = path.resolve(__dirname, "../claude_mnemos/daemon/static/.gitkeep");
      if (!fs.existsSync(gitkeep)) fs.writeFileSync(gitkeep, "");
    },
  };
}

export default defineConfig({
  plugins: [react(), restoreGitkeep()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  build: {
    outDir: "../claude_mnemos/daemon/static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      PROXIED_PREFIXES.map((p) => [p, DAEMON_URL]),
    ),
  },
});

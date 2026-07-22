import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

import { injectCspIntoHtml } from "./src/config/csp";
import { REST_DEV_PROXY_TARGET, WS_DEV_PROXY_TARGET } from "./src/config/endpoints";

// Air-gap invariant (CG-G-00a): the built bundle self-hosts every asset and
// makes zero external-origin requests. Vite already bundles all npm deps at
// build time; this config adds no CDN, no remote font, no external URL. The CSP
// manifest (src/config/csp.ts) is injected into the built index.html here so the
// production artifact enforces same-origin-only.
function cspManifestPlugin(): Plugin {
  return {
    name: "openarm-csp-manifest",
    apply: "build",
    transformIndexHtml(html) {
      return injectCspIntoHtml(html);
    },
  };
}

export default defineConfig({
  plugins: [react(), cspManifestPlugin()],
  // Assets resolve relative to the served bundle so the SPA works under any
  // backend mount path without a hardcoded absolute origin.
  base: "./",
  build: {
    outDir: "dist",
    assetsDir: "assets",
    // Everything bundled; nothing marked external. An empty external list is the
    // machine form of "no dependency is fetched from another origin at runtime".
    rollupOptions: {
      external: [],
    },
  },
  server: {
    // Dev-only convenience: same-origin in dev by proxying to the FastAPI
    // backend (:8000). Does not affect the built bundle.
    proxy: {
      "/api": { target: REST_DEV_PROXY_TARGET, changeOrigin: true },
      "/ws": { target: WS_DEV_PROXY_TARGET, ws: true, changeOrigin: true },
    },
  },
});

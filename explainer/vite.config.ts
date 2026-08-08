import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// __dirname is not available under Vite's native config loader.
const root = path.dirname(fileURLToPath(import.meta.url));

/**
 * Two build targets, because they have opposite requirements:
 *
 *   pnpm build          -> build/       split assets, hashed + cacheable. For Vercel.
 *   pnpm build:artifact -> artifact/    one self-contained .html. For a Claude
 *                                       artifact, whose CSP blocks any external file.
 */
export default defineConfig(({ mode }) => {
  const single = mode === "artifact";
  return {
    plugins: [react(), ...(single ? [viteSingleFile()] : [])],
    resolve: {
      alias: { "@": path.resolve(root, "./src") },
    },
    build: {
      outDir: single ? "artifact" : "build",
      emptyOutDir: true,
      // the artifact must not emit a separate favicon file to reference
      assetsInlineLimit: single ? 100_000_000 : 4096,
    },
  };
});

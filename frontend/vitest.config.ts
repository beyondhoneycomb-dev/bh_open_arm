import { mergeConfig, defineConfig } from "vitest/config";

import viteConfig from "./vite.config";

// Test config extends the build config so tests transform JSX and resolve
// modules exactly as the app does. jsdom gives the shell tests a DOM; the
// air-gap and static-scan tests read the source tree directly via node fs.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test-setup.ts"],
      include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
      css: false,
    },
  }),
);

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx", "tests/test_*.ts", "tests/test_*.tsx"],
    environment: "node",
  },
});

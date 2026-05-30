import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: [
      "tests/**/*.test.ts",
      "tests/**/*.test.tsx",
      "tests/test_*.ts",
      "tests/test_*.tsx",
      "tests/ux/test_*.ts",
      "tests/ux/test_*.tsx",
      "tests/ui/test_*.ts",
      "tests/ui/test_*.tsx",
    ],
    environment: "node",
    css: true,
  },
});

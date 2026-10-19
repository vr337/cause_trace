import { defineConfig } from "vitest/config";

// 与 vite.config.ts 分开：vitest 自带的 vite 版本与项目 vite 7 的类型不兼容
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    setupFiles: ["src/test-setup.ts"],
  },
});

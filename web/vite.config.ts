import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // 图表库体积大且不常变更，单独分包让首屏只加载工作台必需代码
        manualChunks: {
          echarts: ["echarts/core", "echarts/charts", "echarts/components", "echarts/renderers"],
          react: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 开发期直连归因主服务，避免前端硬编码后端地址
      "/api": { target: "http://127.0.0.1:7300", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:7300", ws: true },
    },
  },
});

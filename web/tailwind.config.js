/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 与原型一致：深蓝灰主色 + 涨跌双色
        ink: {
          50: "#f6f7f9",
          100: "#eceef2",
          200: "#d5d9e2",
          300: "#b0b8c9",
          400: "#8591ab",
          500: "#667491",
          600: "#515d78",
          700: "#424c62",
          800: "#394153",
          900: "#0f172a",
        },
        rise: "#dc2626",
        fall: "#16a34a",
      },
      fontFamily: {
        sans: ["Inter", "PingFang SC", "Microsoft YaHei", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "SFMono-Regular", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};

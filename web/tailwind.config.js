/** @type {import('tailwindcss').Config}

色板取自原型 .pen 的设计变量，保证前端与设计稿逐值一致：
bg/surface/border/text-primary/secondary/tertiary/primary/danger/warning/success 及其 soft 变体。
*/
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        "surface-alt": "var(--color-surface-alt)",
        border: "var(--color-border)",
        "border-strong": "var(--color-border-strong)",
        "text-primary": "var(--color-text-primary)",
        "text-secondary": "var(--color-text-secondary)",
        "text-tertiary": "var(--color-text-tertiary)",
        primary: "var(--color-primary)",
        "primary-deep": "var(--color-primary-deep)",
        "primary-soft": "var(--color-primary-soft)",
        danger: "var(--color-danger)",
        "danger-soft": "var(--color-danger-soft)",
        warning: "var(--color-warning)",
        "warning-soft": "var(--color-warning-soft)",
        success: "var(--color-success)",
        "success-soft": "var(--color-success-soft)",
      },
      fontFamily: {
        sans: ["Inter", "PingFang SC", "Microsoft YaHei", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "SFMono-Regular", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};

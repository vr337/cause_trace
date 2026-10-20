import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/", label: "指标异动大盘" },
  { to: "/workbench", label: "归因工作台" },
  { to: "/events", label: "事件日历" },
  { to: "/dictionary", label: "指标字典" },
  { to: "/reports", label: "报告归档" },
];

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrsurface items-center justify-between border-b border-border bg-white px-5">
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded bg-text-primary font-mono text-xs font-bold text-white">
              ct
            </span>
            <span className="text-sm font-semibold">cause_trace</span>
            <span className="text-xs text-text-tertiary">经营归因分析</span>
          </div>

          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `rounded px-3 py-1.5 text-sm transition-colors ${
                    isActive ? "bg-surface-alt font-medium text-text-primary" : "text-text-secondary hover:text-text-primary"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          <span className="rounded border border-border px-2 py-1 text-xs text-text-secondary">
            电商经营域
          </span>
          <span className="grid h-7 w-7 place-items-center rounded-full bg-border text-xs font-medium text-text-primary">
            分
          </span>
        </div>
      </header>

      <main className="min-h-0 flex-1">{children}</main>
    </div>
  );
}

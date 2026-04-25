import Link from "next/link";
import type { ReactNode } from "react";

const navItems = [
  { href: "/", label: "热点" },
  { href: "/keywords", label: "关键词" },
  { href: "/sources", label: "来源" },
  { href: "/runs", label: "任务" },
  { href: "/notifications", label: "通知" },
  { href: "/settings", label: "设置" },
];

export function ConsoleLayout({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <main className="grid min-h-screen bg-slate-100 text-slate-950 md:grid-cols-[220px_1fr]">
      <aside className="border-b border-slate-300 bg-emerald-50 p-5 md:border-b-0 md:border-r">
        <Link className="mb-7 flex items-center gap-3 font-extrabold" href="/">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-teal-700 text-white">A</span>
          <span>Hotspot Radar</span>
        </Link>
        <nav className="grid grid-cols-3 gap-2 md:grid-cols-1">
          {navItems.map((item) => (
            <Link className="rounded-md px-3 py-2 text-sm font-medium text-slate-600 hover:bg-teal-700/10 hover:text-teal-800" key={item.href} href={item.href}>
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <section className="p-5 md:p-7">
        <header className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-extrabold leading-tight">{title}</h1>
          <div>{actions}</div>
        </header>
        {children}
      </section>
    </main>
  );
}

import type { ReactNode } from "react";
import Link from "next/link";
import "./globals.css";

type Props = {
  children: ReactNode;
};

const navItem = [
  { label: "今日热点", href: "/events" },
  { label: "搜索", href: "/search" },
  { label: "配置", href: "/config" },
  { label: "今日日报", href: "/digest" },
];

export default function RootLayout({ children }: Props) {
  return (
    <html lang="zh-CN">
      <body className="bg-slate-950 text-slate-100">
        <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-6">
          <header className="mb-6 flex items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
            <div className="text-lg font-semibold">AI 热点监控 Console</div>
            <nav className="flex gap-2 text-sm text-slate-200">
              {navItem.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-full border border-slate-700 px-3 py-1 transition hover:border-cyan-300 hover:text-cyan-200"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </header>
          <main className="flex-1 rounded-2xl border border-slate-800 bg-slate-900/50 p-4">{children}</main>
          <footer className="mt-6 text-xs text-slate-400">基于 OpenAPI 契约驱动生成接口层，MVP 仅供内部使用</footer>
        </div>
      </body>
    </html>
  );
}

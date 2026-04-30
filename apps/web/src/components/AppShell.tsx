"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import {
  Bell,
  FileText,
  Gauge,
  ListFilter,
  Radar,
  Search,
  Settings,
  Sparkles,
  Tags,
  Workflow,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/app", label: "总览", icon: Gauge },
  { href: "/app/hotspots", label: "热点", icon: Radar },
  { href: "/app/search", label: "搜索", icon: Search },
  { href: "/app/keywords", label: "关键词", icon: Tags },
  { href: "/app/sources", label: "来源", icon: ListFilter },
  { href: "/app/runs", label: "任务", icon: Workflow },
  { href: "/app/reports", label: "报告", icon: FileText },
  { href: "/app/notifications", label: "通知", icon: Bell },
  { href: "/app/settings", label: "设置", icon: Settings },
];

export function AppShell({ title, description, actions, children }: { title: string; description?: string; actions?: ReactNode; children: ReactNode }) {
  const pathname = usePathname();

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border bg-white/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-4 py-3 md:px-6 lg:px-8">
          <div className="flex min-w-0 items-center justify-between gap-3">
            <Link className="flex min-h-11 min-w-0 items-center gap-3 rounded-md focus:outline-none focus:ring-2 focus:ring-ring" href="/app">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
                <Sparkles className="h-5 w-5" />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-extrabold">AI Hotspot Radar</span>
                <span className="block truncate text-xs font-medium text-muted-foreground">Private SaaS Console</span>
              </span>
            </Link>
            <Button asChild className="shrink-0" size="sm" variant="secondary">
              <Link href="/">官网</Link>
            </Button>
          </div>
          <nav aria-label="主导航" className="flex gap-2 overflow-x-auto pb-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href || (item.href !== "/app" && pathname.startsWith(`${item.href}/`));
              return (
                <Link
                  className={cn(
                    "flex min-h-10 shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring",
                    active && "bg-blue-50 text-primary"
                  )}
                  href={item.href}
                  key={item.href}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      <section className="mx-auto w-full max-w-7xl px-4 py-5 md:px-6 lg:px-8">
        <header className="mb-6 flex min-w-0 flex-col gap-4 border-b border-border pb-5 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-extrabold tracking-normal text-slate-950 md:text-3xl">{title}</h1>
            {description ? <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{description}</p> : null}
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </header>
        {children}
      </section>
    </main>
  );
}

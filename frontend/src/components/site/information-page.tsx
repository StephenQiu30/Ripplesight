import Link from "next/link";

import { WorkspaceHeader } from "@/components/navigation/workspace-header";

export function InformationPage({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <WorkspaceHeader current="site" />
      <main className="mx-auto max-w-3xl px-5 py-10 sm:px-8">
        <h1 className="text-3xl font-medium">{title}</h1>
        <div className="text-muted-foreground mt-8 space-y-6 text-sm leading-7">
          {children}
        </div>
        <nav
          aria-label="站点说明"
          className="mt-12 flex flex-wrap gap-5 text-sm"
        >
          <Link href="/about">关于</Link>
          <Link href="/changelog">变更记录</Link>
          <Link href="/privacy">隐私与本机数据</Link>
          <Link href="/terms">使用与内容许可</Link>
          <Link href="/contact">联系</Link>
          <Link href="/feedback">反馈</Link>
        </nav>
      </main>
    </>
  );
}

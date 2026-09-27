import type { Metadata } from "next";
import { connection } from "next/server";
import Link from "next/link";
import { Suspense } from "react";

import { SourceCapabilityMatrix } from "@/app/sources/components/source-capability-matrix";
import { SourceCoveragePanel } from "@/app/sources/components/source-coverage-panel";
import { BrandLockup } from "@/components/brand/brand-lockup";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "来源覆盖",
  robots: { index: false, follow: false },
};

export default async function SourcesPage() {
  await connection();

  return (
    <div className="bg-background min-h-screen">
      <header className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8 xl:px-16 2xl:px-0">
        <BrandLockup href="/events" />
        <Button asChild variant="ghost" size="navigation">
          <Link href="/events">返回工作台</Link>
        </Button>
      </header>
      <main className="mx-auto max-w-7xl px-5 py-12 sm:px-8 sm:py-16 xl:px-16 2xl:px-0">
        <p className="text-muted-foreground font-mono text-xs tracking-wider uppercase">
          Sources
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
          来源覆盖
        </h1>
        <p className="text-muted-foreground mt-4 max-w-2xl leading-7">
          按来源、能力和时间查看计划到期、实际采集与未确认缺口，再追到任务、内容和热榜快照。
        </p>
        <Suspense fallback={<p className="mt-10">正在准备覆盖查询…</p>}>
          <SourceCoveragePanel />
        </Suspense>
        <SourceCapabilityMatrix />
      </main>
    </div>
  );
}

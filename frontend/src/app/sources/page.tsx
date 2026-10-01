import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { SourcesWorkspace } from "@/app/sources/components/sources-workspace";
import { WorkspaceHeader } from "@/components/navigation/workspace-header";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
  title: "来源设置",
  robots: { index: false, follow: false },
};

export default async function SourcesPage() {
  await connection();

  return (
    <div className="bg-background min-h-screen">
      <WorkspaceHeader current="sources" />
      <main className="mx-auto flex max-w-6xl flex-col gap-10 px-5 py-12 sm:px-8 sm:py-16">
        <div className="flex flex-col gap-3">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            来源设置
          </h1>
          <p className="text-muted-foreground max-w-2xl leading-7">
            管理你的信息来源，按需查看连接能力和采集记录。
          </p>
        </div>
        <Suspense
          fallback={
            <Skeleton aria-label="正在准备来源设置" className="h-64 w-full" />
          }
        >
          <SourcesWorkspace />
        </Suspense>
      </main>
    </div>
  );
}

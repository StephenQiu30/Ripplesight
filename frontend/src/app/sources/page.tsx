import { PageHeader } from "@/components/system/page-header";
import { AuthLink } from "@/components/auth/auth-link";
import { Button } from "@/components/ui/button";
import * as UI from "@/components/ui/content";
import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { SourcesWorkspace } from "@/app/sources/components/sources-workspace";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
  title: "平台接入",
  robots: { index: false, follow: false },
};

export default async function SourcesPage() {
  await connection();

  return (
    <UI.Content className="flex flex-col gap-10">
      <UI.Content className="flex flex-col gap-3">
        <PageHeader
          title={<>平台接入</>}
          description={
            <>
              选择系统内置的平台，配置连接并按需启用或停用。关键词搜索、评论和热榜能力分别标明，配置后可在监控主题中选择来源。
            </>
          }
        />
      </UI.Content>
      <Button asChild variant="outline" className="self-start">
        <AuthLink href="/monitors/new">设置关键词并选择平台</AuthLink>
      </Button>
      <Suspense
        fallback={
          <Skeleton aria-label="正在准备来源设置" className="h-64 w-full" />
        }
      >
        <SourcesWorkspace />
      </Suspense>
    </UI.Content>
  );
}

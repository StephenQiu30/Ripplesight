import * as UI from "@/components/ui/content";
import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { SourcesWorkspace } from "@/app/sources/components/sources-workspace";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
  title: "来源设置",
  robots: { index: false, follow: false },
};

export default async function SourcesPage() {
  await connection();

  return (
    <UI.Content className="flex flex-col gap-10">
      <UI.Content className="flex flex-col gap-3">
        <UI.Heading
          level={1}
          className="text-3xl font-semibold tracking-tight sm:text-4xl"
        >
          来源设置
        </UI.Heading>
        <UI.Text className="text-muted-foreground max-w-2xl leading-7">
          管理你的信息来源，按需查看连接能力和采集记录。
        </UI.Text>
      </UI.Content>
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

"use client";

import { useRouter, useSearchParams } from "next/navigation";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { SourceCoveragePanel } from "./source-coverage-panel";
import { SourceSettings } from "./source-settings";

export function SourcesWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const tab =
    requestedTab === "settings"
      ? "settings"
      : requestedTab === "coverage" ||
          searchParams.has("start") ||
          searchParams.has("window")
        ? "coverage"
        : "settings";

  return (
    <Tabs
      value={tab}
      onValueChange={(value) => {
        const params = new URLSearchParams(searchParams.toString());
        params.set("tab", value);
        router.replace(`/sources?${params.toString()}`, { scroll: false });
      }}
      className="gap-8"
    >
      <TabsList variant="line" aria-label="来源管理">
        <TabsTrigger value="settings">连接设置</TabsTrigger>
        <TabsTrigger value="coverage">采集覆盖</TabsTrigger>
      </TabsList>
      <TabsContent value="settings">
        <SourceSettings />
      </TabsContent>
      <TabsContent value="coverage">
        <SourceCoveragePanel />
      </TabsContent>
    </Tabs>
  );
}

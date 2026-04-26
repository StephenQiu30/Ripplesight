import { AppShell } from "@/components/AppShell";
import { KeywordsClient } from "@/components/KeywordsClient";

export default function AppKeywordsPage() {
  return (
    <AppShell description="维护监控关键词和查询模板，控制热点检测的输入。" title="关键词">
      <KeywordsClient />
    </AppShell>
  );
}

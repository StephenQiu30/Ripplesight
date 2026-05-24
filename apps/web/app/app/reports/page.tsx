import { AppShell } from "@/components/AppShell";
import { ReportsClient } from "@/components/ReportsClient";

export default function AppReportsPage() {
  return (
    <AppShell description="生成、预览和发送 daily / weekly 报告，只聚合 active 热点。" title="报告中心">
      <ReportsClient />
    </AppShell>
  );
}

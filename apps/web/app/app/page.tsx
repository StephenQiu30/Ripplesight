import { AppShell } from "@/components/AppShell";
import { DashboardClient } from "@/components/DashboardClient";

export default function AppDashboardPage() {
  return (
    <AppShell description="从这里查看检测运行状态、活跃热点、报告和通知健康度。" title="工作台总览">
      <DashboardClient />
    </AppShell>
  );
}

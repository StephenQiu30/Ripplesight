import { AppShell } from "@/components/AppShell";
import { RunsClient } from "@/components/RunsClient";

export default function AppRunsPage() {
  return (
    <AppShell description="手动触发检测任务并追踪成功、失败和运行状态。" title="任务">
      <RunsClient />
    </AppShell>
  );
}

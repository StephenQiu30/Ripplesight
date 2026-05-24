import { AppShell } from "@/components/AppShell";
import { AnalyticsClient } from "@/components/AnalyticsClient";

export default function AppAnalyticsPage() {
  return (
    <AppShell description="按天趋势、来源排行与 AI 重要性分布分析热点状态。"
      title="趋势分析">
      <AnalyticsClient />
    </AppShell>
  );
}

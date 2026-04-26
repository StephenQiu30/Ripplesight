import { AppShell } from "@/components/AppShell";
import { HotspotsClient } from "@/components/HotspotsClient";

export default function AppHotspotsPage() {
  return (
    <AppShell description="浏览 AI 分析后的热点，按重要性和相关性快速筛选。" title="热点">
      <HotspotsClient />
    </AppShell>
  );
}

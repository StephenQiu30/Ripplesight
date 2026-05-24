import { AppShell } from "@/components/AppShell";
import { HotspotDetailClient } from "@/components/HotspotDetailClient";

export default function AppHotspotDetailPage({ params }: { params: { id: string } }) {
  return (
    <AppShell description="查看来源、关键词、AI 摘要、真实性和相关性理由。" title="热点详情">
      <HotspotDetailClient id={params.id} />
    </AppShell>
  );
}

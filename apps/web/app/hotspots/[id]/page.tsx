import { ConsoleLayout } from "../../../src/components/ConsoleLayout";
import { HotspotDetailClient } from "../../../src/components/HotspotDetailClient";

export default function HotspotDetailPage({ params }: { params: { id: string } }) {
  return (
    <ConsoleLayout title="热点详情">
      <HotspotDetailClient id={params.id} />
    </ConsoleLayout>
  );
}

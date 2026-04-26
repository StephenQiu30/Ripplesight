import { AppShell } from "@/components/AppShell";
import { ReportDetailClient } from "@/components/ReportDetailClient";

export default function AppReportDetailPage({ params }: { params: { id: string } }) {
  return (
    <AppShell description="查看报告周期、状态、摘要和 Markdown 正文。" title="报告详情">
      <ReportDetailClient id={params.id} />
    </AppShell>
  );
}

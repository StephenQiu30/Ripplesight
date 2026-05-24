import { AppShell } from "@/components/AppShell";
import { SourcesClient } from "@/components/SourcesClient";

export default function AppSourcesPage() {
  return (
    <AppShell description="管理 RSS、Hacker News、X/Twitter、Bing、Bilibili 和 Sogou-style 来源。" title="来源">
      <SourcesClient />
    </AppShell>
  );
}

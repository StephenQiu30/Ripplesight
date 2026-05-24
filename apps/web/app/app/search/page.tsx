import { AppShell } from "@/components/AppShell";
import { SearchClient } from "@/components/SearchClient";

export default function AppSearchPage() {
  return (
    <AppShell description="临时验证主题热度。搜索结果不入库、不发通知，也不会进入报告。" title="即时搜索">
      <SearchClient />
    </AppShell>
  );
}

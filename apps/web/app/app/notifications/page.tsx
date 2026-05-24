import { AppShell } from "@/components/AppShell";
import { NotificationsClient } from "@/components/NotificationsClient";

export default function AppNotificationsPage() {
  return (
    <AppShell description="查看事件邮件与报告邮件的 sent、skipped、failed 状态。" title="通知">
      <NotificationsClient />
    </AppShell>
  );
}

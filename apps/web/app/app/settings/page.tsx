import { AppShell } from "@/components/AppShell";
import { SettingsClient } from "@/components/SettingsClient";

export default function AppSettingsPage() {
  return (
    <AppShell description="编辑非敏感运行设置；敏感凭据仍通过环境变量注入。" title="设置">
      <SettingsClient />
    </AppShell>
  );
}

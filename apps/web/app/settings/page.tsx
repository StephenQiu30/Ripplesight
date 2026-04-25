import { ConsoleLayout } from "../../src/components/ConsoleLayout";
import { SettingsClient } from "../../src/components/SettingsClient";

export default function SettingsPage() {
  return (
    <ConsoleLayout title="设置">
      <SettingsClient />
    </ConsoleLayout>
  );
}

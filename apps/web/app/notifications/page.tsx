import { ConsoleLayout } from "../../src/components/ConsoleLayout";
import { NotificationsClient } from "../../src/components/NotificationsClient";

export default function NotificationsPage() {
  return (
    <ConsoleLayout title="通知">
      <NotificationsClient />
    </ConsoleLayout>
  );
}

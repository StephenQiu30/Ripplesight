import { ConsoleLayout } from "../../src/components/ConsoleLayout";
import { RunsClient } from "../../src/components/RunsClient";

export default function RunsPage() {
  return (
    <ConsoleLayout title="任务">
      <RunsClient />
    </ConsoleLayout>
  );
}

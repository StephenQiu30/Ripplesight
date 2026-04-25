import { ConsoleLayout } from "../../src/components/ConsoleLayout";
import { SourcesClient } from "../../src/components/SourcesClient";

export default function SourcesPage() {
  return (
    <ConsoleLayout title="来源">
      <SourcesClient />
    </ConsoleLayout>
  );
}

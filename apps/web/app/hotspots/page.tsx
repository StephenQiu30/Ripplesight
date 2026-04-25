import { ConsoleLayout } from "../../src/components/ConsoleLayout";
import { HotspotsClient } from "../../src/components/HotspotsClient";

export default function HotspotsPage() {
  return (
    <ConsoleLayout title="热点">
      <HotspotsClient />
    </ConsoleLayout>
  );
}

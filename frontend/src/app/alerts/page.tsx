import type { Metadata } from "next";
import { connection } from "next/server";
import { AlertsWorkspace } from "@/app/alerts/components/alerts-workspace";

export const metadata: Metadata = {
  title: "突发告警",
  robots: { index: false, follow: false },
};

export default async function AlertsPage() {
  await connection();
  return <AlertsWorkspace />;
}

import type { Metadata } from "next";
import { connection } from "next/server";
import { OperationsWorkspace } from "@/app/operations/components/operations-workspace";
export const metadata: Metadata = {
  title: "运营管理",
  robots: { index: false, follow: false },
};
export default async function OperationsPage() {
  await connection();
  return <OperationsWorkspace />;
}

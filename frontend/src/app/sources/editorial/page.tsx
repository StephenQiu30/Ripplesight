import type { Metadata } from "next";
import { connection } from "next/server";
import { EditorialSourceManager } from "./components/editorial-source-manager";

export const metadata: Metadata = {
  title: "编辑来源配置",
  robots: { index: false, follow: false },
};

export default async function EditorialSourcesPage() {
  await connection();
  return <EditorialSourceManager />;
}

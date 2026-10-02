import type { Metadata } from "next";
import { connection } from "next/server";
import { ModelManager } from "@/app/operations/models/components/model-manager";

export const metadata: Metadata = {
  title: "模型配置与费用",
  robots: { index: false, follow: false },
};

export default async function ModelsPage() {
  await connection();
  return <ModelManager />;
}

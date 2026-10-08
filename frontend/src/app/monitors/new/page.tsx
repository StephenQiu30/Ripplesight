import type { Metadata } from "next";
import { connection } from "next/server";

import { TopicForm } from "@/app/monitors/new/components/topic-form";

export const metadata: Metadata = {
  title: "新建监控主题",
  robots: { index: false, follow: false },
};

export default async function NewMonitorTopicPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[] }>;
}) {
  await connection();
  const { q } = await searchParams;
  const initialKeywords =
    typeof q === "string" && q.length <= 200 ? q.trim() : "";
  return <TopicForm initialKeywords={initialKeywords} />;
}

import type { Metadata } from "next";
import { connection } from "next/server";

import { TopicForm } from "@/app/monitors/new/components/topic-form";

export const metadata: Metadata = {
  title: "新建监控主题",
  robots: { index: false, follow: false },
};

export default async function NewMonitorTopicPage() {
  await connection();
  return <TopicForm />;
}

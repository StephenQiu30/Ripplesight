import type { Metadata } from "next";

import { TopicsWorkspace } from "@/app/topics/components/topics-workspace";

export const metadata: Metadata = {
  title: "监控主题详情",
  robots: { index: false, follow: false },
};

type MonitorTopicPageProps = {
  params: Promise<{ topicId: string }>;
};

export default async function MonitorTopicPage({
  params,
}: MonitorTopicPageProps) {
  const { topicId } = await params;
  return <TopicsWorkspace topicId={topicId} />;
}

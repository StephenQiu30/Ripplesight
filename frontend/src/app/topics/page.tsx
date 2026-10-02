import type { Metadata } from "next";
import { connection } from "next/server";

import { TopicsWorkspace } from "@/app/topics/components/topics-workspace";

export const metadata: Metadata = {
  title: "我的关注",
  robots: {
    index: false,
    follow: false,
  },
};

export default async function TopicsPage() {
  await connection();

  return <TopicsWorkspace />;
}

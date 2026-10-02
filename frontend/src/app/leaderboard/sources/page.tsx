import type { Metadata } from "next";
import { connection } from "next/server";
import { publicSiteMetadata } from "@/components/publication/site-metadata";

import { listLeaderboardSources } from "@/api/moxingbang";
import { SourcesReading } from "@/app/leaderboard/sources/components/sources-reading";
import { LeaderboardFailure } from "@/components/leaderboard/reading-parts";

export async function generateMetadata(): Promise<Metadata> {
  let indexable = false;
  try {
    const data = await listLeaderboardSources({
      baseURL: process.env.HOTKEY_API_ORIGIN ?? "http://127.0.0.1:8867",
    });
    indexable = data.groups.length > 0;
  } catch {
    // Do not index an unavailable source directory.
  }
  return publicSiteMetadata({
    title: "模型榜评测来源",
    path: "/leaderboard/sources",
    imagePath: "/og/pages/leaderboard.png",
    indexable,
  });
}

export default async function LeaderboardSourcesPage() {
  await connection();
  let data: HotKeyAPI.SourcesView;
  try {
    data = await listLeaderboardSources({
      baseURL: process.env.HOTKEY_API_ORIGIN ?? "http://127.0.0.1:8867",
    });
  } catch (error) {
    return <LeaderboardFailure error={error} href="/leaderboard/sources" />;
  }
  return <SourcesReading data={data} />;
}

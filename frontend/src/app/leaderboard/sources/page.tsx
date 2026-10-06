import type { Metadata } from "next";
import { connection } from "next/server";
import { publicSiteMetadata } from "@/components/publication/site-metadata";
import { listLeaderboardSources } from "@/api/moxingbang";
import { SourcesReading } from "@/app/leaderboard/sources/components/sources-reading";
import { LeaderboardFailure } from "@/components/leaderboard/reading-parts";
import { LeaderboardPageHeader } from "@/components/leaderboard/page-header";
import { Content } from "@/components/ui/content";

export async function generateMetadata(): Promise<Metadata> {
  let indexable = false;
  try {
    const data = await listLeaderboardSources();
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
    data = await listLeaderboardSources();
  } catch (error) {
    return (
      <Content className="flex min-w-0 flex-col gap-6">
        <LeaderboardPageHeader
          title="评测来源与覆盖"
          description="查看评测来源的运营方、用途与证据覆盖。"
        />
        <LeaderboardFailure error={error} href="/leaderboard/sources" />
      </Content>
    );
  }
  return <SourcesReading data={data} />;
}

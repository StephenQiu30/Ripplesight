import type { Metadata } from "next";
import { connection } from "next/server";

import { getLeaderboardSource } from "@/api/moxingbang";
import { publicSiteMetadata } from "@/components/publication/site-metadata";
import { SourceReading } from "@/app/leaderboard/sources/[sourceKey]/components/source-reading";
import { LeaderboardFailure } from "@/components/leaderboard/reading-parts";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ sourceKey: string }>;
}): Promise<Metadata> {
  const { sourceKey } = await params;
  try {
    const data = await getLeaderboardSource({ source_key: sourceKey });
    return publicSiteMetadata({
      title: `${data.full_name} · 评测来源`,
      description: data.source.description,
      path: `/leaderboard/sources/${encodeURIComponent(sourceKey)}`,
      imagePath: "/og/pages/leaderboard.png",
    });
  } catch {
    return { title: "评测来源明细", robots: { index: false, follow: false } };
  }
}

export default async function LeaderboardSourcePage({
  params,
}: {
  params: Promise<{ sourceKey: string }>;
}) {
  await connection();
  const { sourceKey } = await params;
  let data: HotKeyAPI.SourceDetailView;
  try {
    data = await getLeaderboardSource({ source_key: sourceKey });
  } catch (error) {
    return (
      <LeaderboardFailure
        error={error}
        href={`/leaderboard/sources/${encodeURIComponent(sourceKey)}`}
        resource
      />
    );
  }
  return <SourceReading data={data} />;
}

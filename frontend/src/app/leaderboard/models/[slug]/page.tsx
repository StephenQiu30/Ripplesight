import type { Metadata } from "next";
import { connection } from "next/server";

import { getLeaderboardModel } from "@/api/moxingbang";
import { publicSiteMetadata } from "@/components/publication/site-metadata";
import { ModelReading } from "@/app/leaderboard/models/[slug]/components/model-reading";
import { LeaderboardFailure } from "@/components/leaderboard/reading-parts";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  try {
    const data = await getLeaderboardModel({ slug });
    return publicSiteMetadata({
      title: `${data.model.name} · 模型证据`,
      description: `${data.model.name}的公开评测配置、独立证据、排名稳定性与官方价格。`,
      path: `/leaderboard/models/${encodeURIComponent(slug)}`,
      imagePath: "/og/pages/leaderboard.png",
      indexable: !!data.run,
    });
  } catch {
    return { title: "模型证据", robots: { index: false, follow: false } };
  }
}

export default async function ModelPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  await connection();
  const { slug } = await params;
  let data: HotKeyAPI.ModelDetailView;
  try {
    data = await getLeaderboardModel({ slug });
  } catch (error) {
    return (
      <LeaderboardFailure
        error={error}
        href={`/leaderboard/models/${encodeURIComponent(slug)}`}
        resource
      />
    );
  }
  return <ModelReading data={data} />;
}

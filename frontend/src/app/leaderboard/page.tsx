import type { Metadata } from "next";
import { connection } from "next/server";

import { getLeaderboardBoard } from "@/api/moxingbang";
import { publicSiteMetadata } from "@/components/publication/site-metadata";
import { BoardReading } from "@/components/leaderboard/board-reading";
import { LeaderboardFailure } from "@/components/leaderboard/reading-parts";
import { BoardPageFrame } from "@/components/leaderboard/page-header";
import { boardHref } from "@/components/leaderboard/board-navigation";

export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<{ domestic?: string; open_weights?: string }>;
}): Promise<Metadata> {
  const search = await searchParams;
  try {
    const data = await getLeaderboardBoard({ board: "overall" });
    return publicSiteMetadata({
      title: "模型榜",
      description: "查看公开评测共识、证据覆盖、模型价格与来源。",
      path: "/leaderboard",
      imagePath: "/og/pages/leaderboard.png",
      indexable: !!data.run && !search.domestic && !search.open_weights,
    });
  } catch {
    return { title: "模型榜", robots: { index: false, follow: false } };
  }
}

export default async function LeaderboardPage({
  searchParams,
}: {
  searchParams: Promise<{ domestic?: string; open_weights?: string }>;
}) {
  await connection();
  const params = await searchParams;
  const domestic = params.domestic === "true";
  const openWeights = params.open_weights === "true";
  let data: HotKeyAPI.BoardView;
  try {
    data = await getLeaderboardBoard({
      board: "overall",
      domestic,
      open_weights: openWeights,
    });
  } catch (error) {
    return (
      <BoardPageFrame
        board="overall"
        domestic={domestic}
        openWeights={openWeights}
      >
        <LeaderboardFailure
          error={error}
          href={boardHref("overall", domestic, openWeights)}
        />
      </BoardPageFrame>
    );
  }
  return (
    <BoardReading data={data} domestic={domestic} openWeights={openWeights} />
  );
}

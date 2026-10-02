import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import { getLeaderboardBoard } from "@/api/moxingbang";
import { publicSiteMetadata } from "@/components/publication/site-metadata";
import { BoardReading } from "@/components/leaderboard/board-reading";
import { LeaderboardFailure } from "@/components/leaderboard/reading-parts";

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Promise<{ board: string }>;
  searchParams: Promise<{ domestic?: string; open_weights?: string }>;
}): Promise<Metadata> {
  const { board } = await params,
    search = await searchParams;
  if (
    board !== "coding" &&
    board !== "reasoning" &&
    board !== "knowledge" &&
    board !== "professional"
  )
    return { title: "分类模型榜", robots: { index: false, follow: false } };
  try {
    const data = await getLeaderboardBoard({ board });
    return publicSiteMetadata({
      title: `${data.board.name}模型榜`,
      description: data.board.description,
      path: `/leaderboard/category/${board}`,
      imagePath: "/og/pages/leaderboard.png",
      indexable: !!data.run && !search.domestic && !search.open_weights,
    });
  } catch {
    return { title: "分类模型榜", robots: { index: false, follow: false } };
  }
}

export default async function CategoryBoardPage({
  params,
  searchParams,
}: {
  params: Promise<{ board: string }>;
  searchParams: Promise<{ domestic?: string; open_weights?: string }>;
}) {
  await connection();
  const { board } = await params;
  if (
    board !== "coding" &&
    board !== "reasoning" &&
    board !== "knowledge" &&
    board !== "professional"
  )
    notFound();
  const search = await searchParams;
  const domestic = search.domestic === "true";
  const openWeights = search.open_weights === "true";
  let data: HotKeyAPI.BoardView;
  try {
    data = await getLeaderboardBoard({
      board,
      domestic,
      open_weights: openWeights,
    });
  } catch (error) {
    return (
      <LeaderboardFailure
        error={error}
        href={`/leaderboard/category/${board}`}
      />
    );
  }
  return (
    <BoardReading data={data} domestic={domestic} openWeights={openWeights} />
  );
}

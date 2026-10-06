type BoardKey = HotKeyAPI.BoardMetaView["key"];

// Existing public routes remain available without a published run.
export const boardTabs: HotKeyAPI.BoardTabView[] = [
  { key: "overall", name: "综合", href: "/leaderboard" },
  { key: "coding", name: "编程", href: "/leaderboard/category/coding" },
  { key: "reasoning", name: "推理", href: "/leaderboard/category/reasoning" },
  { key: "knowledge", name: "知识", href: "/leaderboard/category/knowledge" },
  {
    key: "professional",
    name: "专业",
    href: "/leaderboard/category/professional",
  },
];

export function boardHref(
  board: BoardKey,
  domestic = false,
  openWeights = false,
) {
  return filteredBoardHref(
    board === "overall" ? "/leaderboard" : `/leaderboard/category/${board}`,
    domestic,
    openWeights,
  );
}

export function filteredBoardHref(
  href: string,
  domestic: boolean,
  openWeights: boolean,
) {
  const query = new URLSearchParams();
  if (domestic) query.set("domestic", "true");
  if (openWeights) query.set("open_weights", "true");
  return query.size ? `${href}?${query}` : href;
}

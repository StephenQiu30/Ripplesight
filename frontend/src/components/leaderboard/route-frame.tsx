"use client";

import type { ReactNode } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import * as UI from "@/components/ui/content";
import { boardTabs } from "./board-navigation";
import { BoardPageFrame, LeaderboardPageHeader } from "./page-header";

// Route boundaries do not receive page params or data. Keep their heading and
// filters available from the current URL while the page is loading or fails.
export function LeaderboardRouteFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/leaderboard";
  const search = useSearchParams();
  if (
    pathname === "/leaderboard" ||
    pathname.startsWith("/leaderboard/category/")
  ) {
    return (
      <BoardPageFrame
        board={boardTabs.find((tab) => tab.href === pathname)?.key ?? "overall"}
        domestic={search?.get("domestic") === "true"}
        openWeights={search?.get("open_weights") === "true"}
      >
        {children}
      </BoardPageFrame>
    );
  }
  const title = pathname.startsWith("/leaderboard/models/")
    ? "模型证据"
    : pathname.startsWith("/leaderboard/sources/")
      ? "评测来源明细"
      : pathname === "/leaderboard/sources"
        ? "评测来源与覆盖"
        : pathname === "/leaderboard/rules"
          ? "计算规则与证据边界"
          : "模型榜";
  return (
    <UI.Content className="flex min-w-0 flex-col gap-6">
      <LeaderboardPageHeader title={title} />
      {children}
    </UI.Content>
  );
}

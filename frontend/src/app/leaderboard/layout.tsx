import Link from "next/link";
import type { ReactNode } from "react";

import { WorkspaceHeader } from "@/components/navigation/workspace-header";

export default function LeaderboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <>
      <WorkspaceHeader current="leaderboard" />
      <nav
        aria-label="模型榜阅读入口"
        className="mx-auto flex max-w-6xl flex-wrap gap-5 px-5 pt-4 text-sm sm:px-8"
      >
        <Link
          className="text-muted-foreground hover:text-foreground"
          href="/leaderboard"
        >
          模型榜
        </Link>
        <Link
          className="text-muted-foreground hover:text-foreground"
          href="/leaderboard/sources"
        >
          评测来源
        </Link>
        <Link
          className="text-muted-foreground hover:text-foreground"
          href="/leaderboard/rules"
        >
          计算规则
        </Link>
      </nav>
      {children}
    </>
  );
}

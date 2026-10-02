import Link from "next/link";
import type { ReactNode } from "react";

export default function LeaderboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <>
      <nav
        aria-label="模型榜阅读入口"
        className="mb-8 flex flex-wrap gap-5 text-sm"
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

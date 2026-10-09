import { PageHeader } from "@/components/system/page-header";
import type { ReactNode } from "react";

import * as UI from "@/components/ui/content";
import { BoardFilters } from "./board-filters";
import { evidenceDate } from "./reading-parts";

export function LeaderboardPageHeader({
  title = "模型榜",
  description = "汇总公开评测 · 按已发布证据更新",
  run,
  actions,
}: {
  title?: string;
  description?: string;
  run?: HotKeyAPI.RunView | null;
  actions?: ReactNode;
}) {
  return (
    <PageHeader
      title={title}
      description={
        <>
          {description}
          {run ? ` · 发布轮次：${evidenceDate(run.generated_at)}` : ""}
        </>
      }
      actions={actions}
      breadcrumbs={
        title === "模型榜"
          ? undefined
          : [{ label: "模型榜", href: "/leaderboard" }, { label: title }]
      }
    />
  );
}

export function BoardPageFrame({
  board,
  domestic,
  openWeights,
  tabs,
  run,
  children,
}: {
  board: HotKeyAPI.BoardMetaView["key"];
  domestic: boolean;
  openWeights: boolean;
  tabs?: HotKeyAPI.BoardTabView[];
  run?: HotKeyAPI.RunView | null;
  children: ReactNode;
}) {
  return (
    <UI.Content className="flex min-w-0 flex-col gap-6">
      <LeaderboardPageHeader
        run={run}
        actions={
          <BoardFilters
            board={board}
            domestic={domestic}
            openWeights={openWeights}
            tabs={tabs}
          />
        }
      />
      {children}
    </UI.Content>
  );
}

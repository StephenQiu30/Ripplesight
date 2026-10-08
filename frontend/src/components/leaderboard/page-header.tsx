import type { ReactNode } from "react";

import * as UI from "@/components/ui/content";
import { BoardFilters } from "./board-filters";
import { evidenceDate } from "./reading-parts";

export function LeaderboardPageHeader({
  title = "模型榜",
  description = "汇总公开评测 · 按已发布证据更新",
  run,
}: {
  title?: string;
  description?: string;
  run?: HotKeyAPI.RunView | null;
}) {
  return (
    <UI.Content as="header" className="flex min-w-0 flex-1 flex-col gap-1">
      <UI.Heading level={1}>{title}</UI.Heading>
      <UI.Text tone="muted" size="sm">
        {description}
        {run ? ` · 发布轮次：${evidenceDate(run.generated_at)}` : ""}
      </UI.Text>
    </UI.Content>
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
      <UI.Content className="flex min-w-0 flex-col justify-between gap-5 xl:flex-row xl:items-center">
        <LeaderboardPageHeader run={run} />
        <BoardFilters
          board={board}
          domestic={domestic}
          openWeights={openWeights}
          tabs={tabs}
        />
      </UI.Content>
      {children}
    </UI.Content>
  );
}

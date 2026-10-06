import type { ReactNode } from "react";

import * as UI from "@/components/ui/content";
import { BoardFilters } from "./board-filters";
import { RunStamp } from "./reading-parts";

export function LeaderboardPageHeader({
  title = "模型榜",
  description = "阅读公开模型排名、证据覆盖与官方价格，并核对评测来源和计算规则。",
  run,
}: {
  title?: string;
  description?: string;
  run?: HotKeyAPI.RunView | null;
}) {
  return (
    <UI.Content as="header" className="flex flex-col gap-3">
      <UI.Heading level={1}>{title}</UI.Heading>
      <UI.Text tone="muted">{description}</UI.Text>
      {run ? <RunStamp run={run} /> : null}
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
      <LeaderboardPageHeader run={run} />
      <BoardFilters
        board={board}
        domestic={domestic}
        openWeights={openWeights}
        tabs={tabs}
      />
      {children}
    </UI.Content>
  );
}

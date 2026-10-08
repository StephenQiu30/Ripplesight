"use client";
import { useRouter } from "next/navigation";
import { Content } from "@/components/ui/content";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { boardHref } from "./board-navigation";
export function BoardFilters({
  board,
  domestic,
  openWeights,
}: {
  board: HotKeyAPI.BoardMetaView["key"];
  domestic: boolean;
  openWeights: boolean;
  tabs?: HotKeyAPI.BoardTabView[];
}) {
  const router = useRouter();
  return (
    <Content className="hide-scrollbar min-w-0 overflow-x-auto py-1">
      <ToggleGroup
        type="single"
        size="default"
        aria-label="榜单维度"
        value={openWeights ? "open" : board}
        onValueChange={(value) => {
          if (value === "overall" || value === "coding")
            router.push(boardHref(value, domestic, false));
          if (value === "open")
            router.push(boardHref("overall", domestic, true));
        }}
      >
        <ToggleGroupItem value="overall">综合</ToggleGroupItem>
        <ToggleGroupItem value="coding">编程</ToggleGroupItem>
        <ToggleGroupItem value="context" disabled title="暂无长上下文榜单数据">
          长上下文
        </ToggleGroupItem>
        <ToggleGroupItem value="open" title="筛选已提供开放权重的模型">
          开源
        </ToggleGroupItem>
      </ToggleGroup>
    </Content>
  );
}

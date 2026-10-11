"use client";

import { ChevronDownIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import * as UI from "@/components/ui/content";

const CONDITION_LABELS: Record<
  HotKeyAPI.SourceSearchConditionView["condition"],
  string
> = {
  match_any: "任意命中",
  match_all: "全部包含",
  exclude: "排除词",
  language: "语言",
  window: "搜索窗口",
};
const HANDLING_LABELS: Record<
  HotKeyAPI.SourceSearchConditionView["handling"],
  string
> = {
  upstream_and_local: "上游候选 + 本地精筛",
  local_only: "仅本地精筛",
  unsupported: "当前路径不支持",
};

/** Explain current source semantics without implying admission or a past receipt. */
export function SourceSearchContract({
  sourceName,
  contract,
  connectionVersion,
}: {
  sourceName: string;
  contract?: HotKeyAPI.SourceSearchContractView | null;
  connectionVersion?: number | null;
}) {
  const current =
    contract?.version === "keyword-search.v1" ? contract : undefined;
  return (
    <Collapsible>
      <CollapsibleTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="navigation"
          className="w-full justify-between text-left whitespace-normal"
          aria-label={`${sourceName}查询范围与筛选`}
        >
          查询范围与筛选 <ChevronDownIcon data-icon="inline-end" />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent motion="height">
        <UI.Content className="flex min-w-0 flex-col gap-3 pt-3 text-sm leading-6 wrap-anywhere">
          {current ? (
            <>
              <UI.Text className="font-medium">{current.path_label}</UI.Text>
              <UI.Text tone="muted">
                {current.basis === "connection"
                  ? connectionVersion != null
                    ? `当前连接 v${connectionVersion}`
                    : "当前连接；版本未知"
                  : current.basis === "preset"
                    ? "预设路径说明，尚未配置"
                    : "尚未配置可识别的查询路径"}
              </UI.Text>
              <UI.Text>{current.query_description}</UI.Text>
              <UI.Text>{current.scope_description}</UI.Text>
              <UI.Content as="dl" className="flex flex-col gap-3">
                {current.conditions.map((condition) => (
                  <UI.Content key={condition.condition}>
                    <UI.Content as="dt" className="font-medium">
                      {CONDITION_LABELS[condition.condition] ?? "未知条件"}
                      {" · "}
                      {HANDLING_LABELS[condition.handling] ?? "处理方式未知"}
                    </UI.Content>
                    <UI.Content as="dd">{condition.explanation}</UI.Content>
                  </UI.Content>
                ))}
              </UI.Content>
              <UI.ContentList className="flex list-disc flex-col gap-2 pl-5">
                {current.limitations.map((limitation) => (
                  <UI.ContentListItem key={limitation}>
                    {limitation}
                  </UI.ContentListItem>
                ))}
              </UI.ContentList>
            </>
          ) : (
            <UI.Text>
              查询处理未知：未保存可识别的查询条件说明，请刷新来源状态。不能据此判断上游是否支持这些条件。
            </UI.Text>
          )}
          <UI.Text tone="muted">
            这里只解释当前路径；准入、预算和采集完成以实际回执为准。
          </UI.Text>
        </UI.Content>
      </CollapsibleContent>
    </Collapsible>
  );
}

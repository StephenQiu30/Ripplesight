"use client";

import { useId } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { boardHref, boardTabs, filteredBoardHref } from "./board-navigation";
import * as UI from "@/components/ui/content";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

export function BoardFilters({
  board,
  domestic,
  openWeights,
  tabs = boardTabs,
}: {
  board: HotKeyAPI.BoardMetaView["key"];
  domestic: boolean;
  openWeights: boolean;
  tabs?: HotKeyAPI.BoardTabView[];
}) {
  const router = useRouter();
  const fieldId = useId();
  const href = boardHref(board);
  return (
    <UI.Content className="flex w-full min-w-0 flex-col gap-4 xl:w-80 xl:shrink-0">
      <UI.Content className="hide-scrollbar min-w-0 overflow-x-auto py-1">
        <ToggleGroup
          type="single"
          value={board}
          size="sm"
          aria-label="榜单维度"
          onValueChange={(key) => {
            const tab = tabs.find((item) => item.key === key);
            if (tab)
              router.push(filteredBoardHref(tab.href, domestic, openWeights));
          }}
        >
          {tabs.map((tab) => (
            <ToggleGroupItem key={tab.key} value={tab.key}>
              {tab.name}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </UI.Content>
      <UI.Form
        key={`${board}-${domestic}-${openWeights}`}
        action={href}
        method="get"
        aria-label="模型筛选"
      >
        <FieldGroup className="flex flex-row flex-wrap items-center gap-4">
          <Field orientation="horizontal" className="w-auto">
            <Checkbox
              name="domestic"
              value="true"
              defaultChecked={domestic}
              id={`${fieldId}-domestic`}
            />
            <FieldLabel htmlFor={`${fieldId}-domestic`}>国内模型</FieldLabel>
          </Field>
          <Field orientation="horizontal" className="w-auto">
            <Checkbox
              name="open_weights"
              value="true"
              defaultChecked={openWeights}
              id={`${fieldId}-open-weights`}
            />
            <FieldLabel htmlFor={`${fieldId}-open-weights`}>
              开放权重
            </FieldLabel>
          </Field>
          <Button type="submit" variant="secondary" size="sm">
            应用筛选
          </Button>
          {domestic || openWeights ? (
            <Button asChild variant="link" size="sm">
              <Link href={href}>清除筛选</Link>
            </Button>
          ) : null}
        </FieldGroup>
      </UI.Form>
    </UI.Content>
  );
}

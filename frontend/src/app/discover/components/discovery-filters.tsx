"use client";

import { useId, useState } from "react";
import { ChevronDownIcon, SearchIcon } from "lucide-react";
import * as UI from "@/components/ui/content";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

function FilterChoice({
  label,
  name,
  value,
  onChange,
  options,
}: {
  label: string;
  name: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly (readonly [string, string])[];
}) {
  const id = useId();
  return (
    <Field className="w-auto min-w-0">
      <FieldLabel htmlFor={id} className="sr-only">
        {label}
      </FieldLabel>
      <Input type="hidden" name={name} value={value} />
      <Select
        value={value || "__none__"}
        onValueChange={(next) => onChange(next === "__none__" ? "" : next)}
      >
        <SelectTrigger id={id} className="w-full min-w-32">
          <UI.Text as="span" tone="muted" size="xs">
            {label}
          </UI.Text>
          <SelectValue />
        </SelectTrigger>
        <SelectContent position="popper">
          <SelectGroup>
            <SelectLabel className="sr-only">{label}</SelectLabel>
            {options.map(([key, title]) => (
              <SelectItem key={key} value={key || "__none__"}>
                {title}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </Field>
  );
}

export function DiscoveryFilters({
  mode,
  window,
  category,
  channel,
  by,
  params,
  categories,
  sources = [],
}: {
  mode: "selected" | "all";
  window: "24h" | "7d";
  category?: string;
  channel?: string;
  by: "timeline" | "published";
  params: Record<string, string | undefined>;
  categories: readonly (readonly [string, string])[];
  sources?: readonly { key: string; name: string }[];
}) {
  const id = useId();
  const [selectedMode, setMode] = useState(mode);
  const [selectedWindow, setWindow] = useState(window);
  const [selectedCategory, setCategory] = useState(category ?? "");
  const [selectedChannel, setChannel] = useState(channel ?? "");
  const [selectedSource, setSource] = useState(params.source_key ?? "");
  const [selectedBy, setBy] = useState<string>(by);
  const [order, setOrder] = useState(
    params.search_order === "time" ? "time" : "relevance",
  );
  const [advancedOpen, setAdvancedOpen] = useState(
    Boolean(
      category ||
      channel ||
      by === "published" ||
      params.source_key ||
      params.tag ||
      params.topic,
    ),
  );
  const sourceOptions: [string, string][] = [
    ["", "全部来源"],
    ...sources.map(({ key, name }): [string, string] => [key, name]),
  ];
  if (
    selectedSource &&
    !sources.some((source) => source.key === selectedSource)
  )
    sourceOptions.push([selectedSource, "指定来源（暂无可读资料）"]);
  return (
    <UI.Form
      action="/discover"
      method="get"
      role="search"
      aria-label="公开资讯检索"
      className="flex min-w-0 flex-col gap-3"
    >
      <FieldGroup className="flex-row items-center gap-2">
        <Field className="min-w-0 flex-1">
          <FieldLabel htmlFor={id} className="sr-only">
            检索
          </FieldLabel>
          <InputGroup className="h-12">
            <InputGroupAddon className="pl-4">
              <SearchIcon aria-hidden="true" />
            </InputGroupAddon>
            <InputGroupInput
              id={id}
              type="search"
              name="q"
              defaultValue={params.q}
              maxLength={200}
              placeholder="搜索事件、主题或来源"
            />
          </InputGroup>
        </Field>
        <Button type="submit" size="search">
          搜索
        </Button>
      </FieldGroup>
      <Input type="hidden" name="mode" value={selectedMode} />
      <Input type="hidden" name="category" value={selectedCategory} />
      <Collapsible
        open={advancedOpen}
        onOpenChange={setAdvancedOpen}
        className="flex min-w-0 flex-col gap-4"
      >
        <UI.Content className="flex flex-wrap items-center gap-2">
          <UI.Content className="hide-scrollbar min-w-0 overflow-x-auto py-1">
            <ToggleGroup
              type="single"
              value={selectedMode}
              aria-label="范围"
              onValueChange={(value) => {
                if (value === "all" || value === "selected") setMode(value);
              }}
            >
              <ToggleGroupItem value="all">全部资讯</ToggleGroupItem>
              <ToggleGroupItem value="selected">精选</ToggleGroupItem>
            </ToggleGroup>
          </UI.Content>
          <FilterChoice
            label="时间"
            name="window"
            value={selectedWindow}
            onChange={(value) => setWindow(value === "7d" ? "7d" : "24h")}
            options={[
              ["24h", "过去 24 小时"],
              ["7d", "过去 7 天"],
            ]}
          />
          <FilterChoice
            label="搜索排序"
            name="search_order"
            value={order}
            onChange={setOrder}
            options={[
              ["relevance", "相关性"],
              ["time", "最新时间"],
            ]}
          />
          <CollapsibleTrigger asChild>
            <Button type="button" variant="ghost">
              高级筛选
              <ChevronDownIcon data-icon="inline-end" />
            </Button>
          </CollapsibleTrigger>
        </UI.Content>
        <CollapsibleContent forceMount className="data-[state=closed]:hidden">
          <FieldGroup className="gap-4">
            <Field>
              <FieldLabel id={`${id}-category`}>分类</FieldLabel>
              <UI.Content className="hide-scrollbar min-w-0 overflow-x-auto py-1">
                <ToggleGroup
                  type="single"
                  value={selectedCategory || "__all__"}
                  aria-labelledby={`${id}-category`}
                  onValueChange={(value) => {
                    if (value) setCategory(value === "__all__" ? "" : value);
                  }}
                >
                  <ToggleGroupItem value="__all__">全部分类</ToggleGroupItem>
                  {categories.map(([key, label]) => (
                    <ToggleGroupItem key={key} value={key}>
                      {label}
                    </ToggleGroupItem>
                  ))}
                </ToggleGroup>
              </UI.Content>
            </Field>
            <UI.Content className="grid grid-cols-2 gap-3 lg:grid-cols-3">
              <FilterChoice
                label="频道"
                name="channel"
                value={selectedChannel}
                onChange={setChannel}
                options={[
                  ["", "全部频道"],
                  ["news", "资讯"],
                  ["x", "X"],
                  ["firstParty", "第一方"],
                ]}
              />
              <FilterChoice
                label="排列"
                name="by"
                value={selectedBy}
                onChange={setBy}
                options={[
                  ["timeline", "发现时间线"],
                  ["published", "来源发布时间"],
                ]}
              />
              <FilterChoice
                label="来源"
                name="source_key"
                value={selectedSource}
                onChange={setSource}
                options={sourceOptions}
              />
              <Field>
                <FieldLabel htmlFor={`${id}-tag`}>标签</FieldLabel>
                <Input
                  id={`${id}-tag`}
                  name="tag"
                  defaultValue={params.tag}
                  maxLength={128}
                  placeholder="正式标签"
                />
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-topic`}>专题</FieldLabel>
                <Input
                  id={`${id}-topic`}
                  name="topic"
                  defaultValue={params.topic}
                  maxLength={64}
                  placeholder="专题标识，如 openai"
                />
              </Field>
            </UI.Content>
          </FieldGroup>
        </CollapsibleContent>
      </Collapsible>
    </UI.Form>
  );
}

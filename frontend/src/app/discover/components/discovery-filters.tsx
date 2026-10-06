"use client";
import * as UI from "@/components/ui/content";

import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ChevronDownIcon, SearchIcon } from "lucide-react";
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
  SelectLabel,
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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
  const fieldId = useId();

  const [selectedMode, setSelectedMode] = useState(mode);
  const [selectedWindow, setSelectedWindow] = useState(window);
  const [selectedCategory, setSelectedCategory] = useState(category ?? "");
  const [selectedChannel, setSelectedChannel] = useState(channel ?? "");
  const [selectedSource, setSelectedSource] = useState(params.source_key ?? "");
  const [advancedOpen, setAdvancedOpen] = useState(
    Boolean(
      channel ||
      by === "published" ||
      params.source_key ||
      params.tag ||
      params.topic ||
      params.search_order === "time",
    ),
  );
  return (
    <UI.Form
      action="/discover"
      method="get"
      role="search"
      aria-label="公开资讯检索"
      className="flex flex-col gap-4"
    >
      <FieldGroup className="flex-row items-center gap-2">
        <Field className="min-w-0 flex-1">
          <FieldLabel htmlFor={`${fieldId}-page-field-10`} className="sr-only">
            检索
          </FieldLabel>
          <InputGroup className="h-14">
            <InputGroupAddon className="pl-4">
              <SearchIcon aria-hidden="true" />
            </InputGroupAddon>
            <InputGroupInput
              type="search"
              name="q"
              defaultValue={params.q}
              maxLength={200}
              placeholder="搜索公开资讯"
              id={`${fieldId}-page-field-10`}
            />
          </InputGroup>
        </Field>
        <Button type="submit" size="xl">
          查看
        </Button>
      </FieldGroup>
      <Input type="hidden" name="mode" value={selectedMode} />
      <Input type="hidden" name="window" value={selectedWindow} />
      <Input type="hidden" name="category" value={selectedCategory} />
      <FieldGroup className="gap-4">
        <Field>
          <FieldLabel id={`${fieldId}-category-label`}>分类</FieldLabel>
          <UI.Content className="hide-scrollbar max-w-full overflow-x-auto py-1">
            <ToggleGroup
              type="single"
              value={selectedCategory || "__all__"}
              onValueChange={(value) => {
                if (value)
                  setSelectedCategory(value === "__all__" ? "" : value);
              }}
              aria-labelledby={`${fieldId}-category-label`}
              className="min-w-max"
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
        <UI.Content className="flex flex-wrap gap-4">
          <Field className="w-auto">
            <FieldLabel id={`${fieldId}-mode-label`}>范围</FieldLabel>
            <ToggleGroup
              type="single"
              value={selectedMode}
              onValueChange={(value) => {
                if (value === "all" || value === "selected")
                  setSelectedMode(value);
              }}
              aria-labelledby={`${fieldId}-mode-label`}
            >
              <ToggleGroupItem value="all">全部资讯</ToggleGroupItem>
              <ToggleGroupItem value="selected">精选</ToggleGroupItem>
            </ToggleGroup>
          </Field>
          <Field className="w-auto">
            <FieldLabel id={`${fieldId}-window-label`}>时间</FieldLabel>
            <ToggleGroup
              type="single"
              value={selectedWindow}
              onValueChange={(value) => {
                if (value === "24h" || value === "7d") setSelectedWindow(value);
              }}
              aria-labelledby={`${fieldId}-window-label`}
            >
              <ToggleGroupItem value="24h">24 小时</ToggleGroupItem>
              <ToggleGroupItem value="7d">7 天</ToggleGroupItem>
            </ToggleGroup>
          </Field>
        </UI.Content>
      </FieldGroup>
      <UI.Text tone="muted" size="xs">
        选择筛选后点击「查看」，查询条件会保存在地址中。
      </UI.Text>
      <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="navigation"
            className="gap-2"
          >
            高级筛选
            <ChevronDownIcon aria-hidden="true" />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent
          forceMount
          className="pt-3 data-[state=closed]:hidden"
        >
          <FieldGroup className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-page-field-4`}>频道</FieldLabel>
              <Select
                name="channel"
                value={selectedChannel}
                onValueChange={(value) =>
                  setSelectedChannel(value === "__none__" ? "" : value)
                }
              >
                <SelectTrigger
                  size="lg"
                  id={`${fieldId}-page-field-4`}
                  className="w-full min-w-0"
                >
                  <SelectValue placeholder="全部频道" />
                </SelectTrigger>
                <SelectContent position="popper">
                  <SelectGroup>
                    <SelectLabel className="sr-only">频道</SelectLabel>
                    <SelectItem value="__none__" className="whitespace-normal">
                      全部频道
                    </SelectItem>
                    <SelectItem value="news" className="whitespace-normal">
                      资讯
                    </SelectItem>
                    <SelectItem value="x" className="whitespace-normal">
                      X
                    </SelectItem>
                    <SelectItem
                      value="firstParty"
                      className="whitespace-normal"
                    >
                      第一方
                    </SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-page-field-5`}>排列</FieldLabel>
              <Select name="by" defaultValue={by}>
                <SelectTrigger
                  size="lg"
                  id={`${fieldId}-page-field-5`}
                  className="w-full min-w-0"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent position="popper">
                  <SelectGroup>
                    <SelectLabel className="sr-only">排列</SelectLabel>
                    <SelectItem value="timeline" className="whitespace-normal">
                      发现时间线
                    </SelectItem>
                    <SelectItem value="published" className="whitespace-normal">
                      来源发布时间
                    </SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-page-field-6`}>来源</FieldLabel>
              <Select
                name="source_key"
                value={selectedSource}
                onValueChange={(value) =>
                  setSelectedSource(value === "__none__" ? "" : value)
                }
              >
                <SelectTrigger
                  size="lg"
                  id={`${fieldId}-page-field-6`}
                  className="w-full min-w-0"
                >
                  <SelectValue placeholder="全部来源" />
                </SelectTrigger>
                <SelectContent position="popper">
                  <SelectGroup>
                    <SelectLabel className="sr-only">来源</SelectLabel>
                    <SelectItem value="__none__">全部来源</SelectItem>
                    {sources.map((source) => (
                      <SelectItem
                        key={source.key}
                        value={source.key}
                        className="whitespace-normal"
                      >
                        {source.name}
                      </SelectItem>
                    ))}
                    {selectedSource &&
                    !sources.some((source) => source.key === selectedSource) ? (
                      <SelectItem value={selectedSource}>
                        指定来源（暂无可读资料）
                      </SelectItem>
                    ) : null}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-page-field-7`}>标签</FieldLabel>
              <Input
                name="tag"
                defaultValue={params.tag}
                maxLength={128}
                placeholder="正式标签"
                id={`${fieldId}-page-field-7`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-page-field-8`}>专题</FieldLabel>
              <Input
                name="topic"
                defaultValue={params.topic}
                maxLength={64}
                placeholder="专题标识，如 openai"
                id={`${fieldId}-page-field-8`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-page-field-9`}>
                搜索排序
              </FieldLabel>
              <Select
                name="search_order"
                defaultValue={
                  params.search_order === "time" ? "time" : "relevance"
                }
              >
                <SelectTrigger
                  size="lg"
                  id={`${fieldId}-page-field-9`}
                  className="w-full min-w-0"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent position="popper">
                  <SelectGroup>
                    <SelectLabel className="sr-only">搜索排序</SelectLabel>
                    <SelectItem value="relevance" className="whitespace-normal">
                      相关性
                    </SelectItem>
                    <SelectItem value="time" className="whitespace-normal">
                      最新时间
                    </SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
          </FieldGroup>
        </CollapsibleContent>
      </Collapsible>
    </UI.Form>
  );
}

"use client";
import { useEffect, useId } from "react";
import { useRouter } from "next/navigation";
import { SearchIcon } from "lucide-react";
import { Content, Form, Text } from "@/components/ui/content";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useLayoutScrollContainer } from "@/layout/basic-layout";
import { discoveryHref } from "./discovery-data";

export function DiscoveryFilters({
  window,
  params,
  resultCount,
}: {
  resultCount?: number;
  mode: string;
  window: string;
  category?: string;
  channel?: string;
  by: string;
  params: Record<string, string | undefined>;
  categories: readonly (readonly [string, string])[];
  sources?: readonly { key: string; name: string }[];
}) {
  const id = useId();
  const router = useRouter();
  const scroller = useLayoutScrollContainer();
  const locationKey = new URLSearchParams(
    Object.entries(params).filter((entry): entry is [string, string] =>
      Boolean(entry[1]),
    ),
  ).toString();
  useEffect(() => {
    scroller?.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [locationKey, scroller]);
  const canSort = Boolean(params.q?.trim());
  const navigate = (key: string, value: string) =>
    router.push(discoveryHref({ ...params, [key]: value }));
  return (
    <Content layout="stack" className="gap-3">
      <Form action="/discover" role="search" aria-label="公开资讯检索">
        <FieldGroup className="flex-row items-center gap-2">
          <Field className="min-w-0 flex-1">
            <FieldLabel htmlFor={id} className="sr-only">
              检索
            </FieldLabel>
            <InputGroup className="h-12">
              <InputGroupAddon className="pl-4">
                <SearchIcon />
              </InputGroupAddon>
              <InputGroupInput
                id={id}
                name="q"
                type="search"
                defaultValue={params.q}
                maxLength={200}
                placeholder="搜索事件、资讯和评论…"
              />
            </InputGroup>
          </Field>
          <Button type="submit" size="search">
            搜索
          </Button>
        </FieldGroup>
        {Object.entries(params)
          .filter(([key, value]) => value && key !== "q" && key !== "cursor")
          .map(([key, value]) => (
            <Input key={key} name={key} type="hidden" value={value} />
          ))}
      </Form>
      <Content
        role="group"
        aria-label="检索筛选"
        className="flex flex-wrap items-center gap-3"
      >
        <Content className="hide-scrollbar min-w-0 overflow-x-auto">
          <ToggleGroup
            type="single"
            size="default"
            aria-label="内容类型"
            value={params.type ?? "all"}
            onValueChange={(value) => {
              if (value) navigate("type", value);
            }}
          >
            {[
              ["all", "全部"],
              ["events", "事件"],
              ["items", "资讯"],
              ["comments", "评论"],
            ].map(([value, label]) => (
              <ToggleGroupItem value={value} key={value}>
                {label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </Content>
        <Select
          value={window}
          onValueChange={(value) => navigate("window", value)}
        >
          <SelectTrigger aria-label="时间范围" className="w-auto">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="24h">过去 24 小时</SelectItem>
              <SelectItem value="7d">过去 7 天</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <Select value="all" disabled>
          <SelectTrigger aria-label="情感筛选暂不可用" className="w-auto">
            <Text as="span" size="xs" tone="muted">
              情感
            </Text>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="all">全部</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <Select
          value={
            !canSort || params.search_order === "time" ? "time" : "relevance"
          }
          disabled={!canSort}
          onValueChange={(value) => navigate("search_order", value)}
        >
          <SelectTrigger
            aria-label={canSort ? "排序" : "排序：输入关键词后可切换"}
            className="w-auto"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="relevance">相关度</SelectItem>
              <SelectItem value="time">最新时间</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        {resultCount !== undefined ? (
          <Text tone="muted" size="xs" className="ml-auto">
            本页资讯 {resultCount} 条 ·{" "}
            {window === "7d" ? "过去 7 天" : "过去 24 小时"}
          </Text>
        ) : null}
      </Content>
    </Content>
  );
}

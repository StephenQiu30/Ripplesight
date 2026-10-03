"use client";

import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

  const [selectedCategory, setSelectedCategory] = useState(category ?? "");
  const [selectedChannel, setSelectedChannel] = useState(channel ?? "");
  const [selectedSource, setSelectedSource] = useState(params.source_key ?? "");
  return (
    <form method="get" className="my-7">
      <FieldGroup className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field className="min-w-0">
          <FieldLabel htmlFor={`${fieldId}-page-field-1`}>范围</FieldLabel>
          <Select name="mode" defaultValue={mode}>
            <SelectTrigger
              id={`${fieldId}-page-field-1`}
              className="w-full min-w-0"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent position="popper">
              <SelectGroup>
                <SelectLabel className="sr-only">范围</SelectLabel>
                <SelectItem value="selected" className="whitespace-normal">
                  精选
                </SelectItem>
                <SelectItem value="all" className="whitespace-normal">
                  全部
                </SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
        <Field className="min-w-0">
          <FieldLabel htmlFor={`${fieldId}-page-field-2`}>时间</FieldLabel>
          <Select name="window" defaultValue={window}>
            <SelectTrigger
              id={`${fieldId}-page-field-2`}
              className="w-full min-w-0"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent position="popper">
              <SelectGroup>
                <SelectLabel className="sr-only">时间</SelectLabel>
                <SelectItem value="24h" className="whitespace-normal">
                  24 小时
                </SelectItem>
                <SelectItem value="7d" className="whitespace-normal">
                  7 天
                </SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
        <Field className="min-w-0">
          <FieldLabel htmlFor={`${fieldId}-page-field-3`}>分类</FieldLabel>
          <Select
            name="category"
            value={selectedCategory}
            onValueChange={(value) =>
              setSelectedCategory(value === "__none__" ? "" : value)
            }
          >
            <SelectTrigger
              id={`${fieldId}-page-field-3`}
              className="w-full min-w-0"
            >
              <SelectValue placeholder="全部分类" />
            </SelectTrigger>
            <SelectContent position="popper">
              <SelectGroup>
                <SelectLabel className="sr-only">分类</SelectLabel>
                <SelectItem value="__none__" className="whitespace-normal">
                  全部分类
                </SelectItem>
                {categories.map(([key, label]) => (
                  <SelectItem
                    key={key}
                    value={key}
                    className="whitespace-normal"
                  >
                    {label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
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
                <SelectItem value="firstParty" className="whitespace-normal">
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
          <FieldLabel htmlFor={`${fieldId}-page-field-9`}>搜索排序</FieldLabel>
          <Select
            name="search_order"
            defaultValue={params.search_order === "time" ? "time" : "relevance"}
          >
            <SelectTrigger
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
        <Field className="min-w-0 sm:col-span-2">
          <FieldLabel htmlFor={`${fieldId}-page-field-10`}>检索</FieldLabel>
          <Input
            name="q"
            defaultValue={params.q}
            maxLength={200}
            placeholder="所有词项均匹配"
            id={`${fieldId}-page-field-10`}
          />
        </Field>
        <Button type="submit" className="self-end">
          查看
        </Button>
      </FieldGroup>
    </form>
  );
}

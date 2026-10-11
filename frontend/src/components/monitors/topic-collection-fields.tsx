"use client";

import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type TopicFieldErrors } from "./topic-validation";

export type TopicCollectionSettings = Required<
  Pick<
    HotKeyAPI.MonitorTopicCreateInput,
    | "search_language"
    | "search_window_seconds"
    | "max_queries"
    | "max_items_per_query"
    | "max_requests_per_query"
  >
>;
export const DEFAULT_TOPIC_COLLECTION: TopicCollectionSettings = {
  search_language: "any",
  search_window_seconds: 86400,
  max_queries: 50,
  max_items_per_query: 100,
  max_requests_per_query: 100,
};
const LIMITS = [
  ["search_window_seconds", "搜索窗口（秒）", 600, 2592000],
  ["max_queries", "每来源每轮查询上限", 1, 50],
  ["max_items_per_query", "每查询候选处理上限", 1, 2000],
  ["max_requests_per_query", "每查询每轮平台请求上限", 1, 100],
] as const;

export function readTopicCollection(
  value: HotKeyAPI.MonitorTopicView,
): TopicCollectionSettings {
  return {
    search_language: value.search_language ?? "any",
    search_window_seconds: value.search_window_seconds ?? 86400,
    max_queries: value.max_queries ?? 50,
    max_items_per_query: value.max_items_per_query ?? 100,
    max_requests_per_query: value.max_requests_per_query ?? 100,
  };
}

export function validateTopicCollection(
  value: TopicCollectionSettings,
): TopicFieldErrors {
  const errors: TopicFieldErrors = {};
  for (const [key, label, min, max] of LIMITS) {
    if (!Number.isInteger(value[key]) || value[key] < min || value[key] > max)
      errors[key] = `${label}须为 ${min}—${max} 之间的整数。`;
  }
  return errors;
}

export function TopicCollectionFields({
  value,
  onChange,
  disabled,
  fieldErrors = {},
}: {
  value: TopicCollectionSettings;
  onChange: (value: TopicCollectionSettings) => void;
  disabled: boolean;
  fieldErrors?: TopicFieldErrors;
}) {
  return (
    <FieldSet disabled={disabled}>
      <FieldLegend variant="label">关键词采集范围</FieldLegend>
      <FieldGroup className="gap-5">
        <Field>
          <FieldLabel htmlFor="search-language">材料语言</FieldLabel>
          <Select
            value={value.search_language}
            onValueChange={(
              language: TopicCollectionSettings["search_language"],
            ) => onChange({ ...value, search_language: language })}
            disabled={disabled}
          >
            <SelectTrigger
              id="search-language"
              aria-invalid={Boolean(fieldErrors.search_language)}
              aria-describedby="language-help"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="any">不限语言</SelectItem>
                <SelectItem value="zh">中文（本地元数据筛选）</SelectItem>
                <SelectItem value="en">英文（本地元数据筛选）</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
          <FieldDescription id="language-help">
            仅按平台返回的语言标签筛选，不猜测语言。HN、B站和RSS通常不返回标签；指定语言会排除未知材料，可能全部排除，不表示平台无相关内容。
          </FieldDescription>
          {fieldErrors.search_language ? (
            <FieldDescription role="alert">
              {fieldErrors.search_language}
            </FieldDescription>
          ) : null}
        </Field>
        {LIMITS.map(([key, label, min, max]) => (
          <Field key={key} data-invalid={Boolean(fieldErrors[key])}>
            <FieldLabel htmlFor={`collection-${key}`}>{label}</FieldLabel>
            <Input
              id={`collection-${key}`}
              type="number"
              min={min}
              max={max}
              step={1}
              required
              value={value[key]}
              disabled={disabled}
              onChange={(event) =>
                onChange({ ...value, [key]: Number(event.target.value) })
              }
              aria-invalid={Boolean(fieldErrors[key])}
              aria-describedby={
                fieldErrors[key] ? `collection-${key}-error` : "collection-help"
              }
            />
            {fieldErrors[key] ? (
              <FieldDescription id={`collection-${key}-error`} role="alert">
                {fieldErrors[key]}
              </FieldDescription>
            ) : null}
          </Field>
        ))}
      </FieldGroup>
      <FieldDescription id="collection-help">
        窗口独立于采集频率，默认24小时；定时只采窗口内增量，窗口短于频率可能留下间隔。候选处理上限跨页累计，重复和精筛前材料也计入；上游超量返回会裁剪并保留真实观察数；平台实际请求含登录检查等。有效上限取主题与来源安全限制的较小值，人工重试开始新请求轮次。仅作用于关键词搜索。
      </FieldDescription>
    </FieldSet>
  );
}

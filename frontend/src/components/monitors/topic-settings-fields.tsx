"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronDownIcon } from "lucide-react";

import { getReportEmailSubscription } from "@/api/gerenbaogaotongzhi";
import { toast } from "sonner";
import { Item } from "@/components/ui/item";
import { Spinner } from "@/components/ui/spinner";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  SelectLabel,
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { KeywordGroupField } from "./keyword-group-field";
import { type TopicFieldErrors } from "./topic-validation";

export type TopicSourceOption = {
  sourceKey: string;
  displayName: string;
  selectable: boolean;
  reason: string;
};

export function selectableTopicSources(
  platforms: HotKeyAPI.SourcePlatformView[],
  selectedSourceKeys: string[] = [],
): TopicSourceOption[] {
  const available = platforms.flatMap((platform) => {
    const search = platform.capabilities.find(
      (capability) => capability.capability === "search",
    );
    if (!search) return [];
    const status = search.scheduled.status;
    const selectable =
      platform.connection_status === "active" &&
      !platform.has_credentials &&
      (status === "available" || status === "pending_verification");
    return [
      {
        sourceKey: platform.source_key,
        displayName: platform.display_name,
        selectable,
        reason: selectable
          ? status === "available"
            ? "已验证；恢复时还会检查预算。"
            : "预设已应用，待真实采集验证。"
          : search.scheduled.next_action,
      },
    ];
  });
  const availableKeys = new Set(available.map((source) => source.sourceKey));
  return [
    ...available,
    ...selectedSourceKeys
      .filter((key) => !availableKeys.has(key))
      .map((key) => ({
        sourceKey: key,
        displayName: `${key}（当前不可用）`,
        selectable: false,
        reason: "当前来源不在搜索能力列表中，请取消选择。",
      })),
  ];
}

type TopicSettingsFieldsProps = {
  sourceOptions: TopicSourceOption[];
  sourceKeys: string[];
  onSourceKeysChange: (value: string[]) => void;
  disabled: boolean;
  fieldErrors?: TopicFieldErrors;
};

export function TopicSettingsFields({
  sourceOptions,
  sourceKeys,
  onSourceKeysChange,
  disabled,
  fieldErrors = {},
}: TopicSettingsFieldsProps) {
  function toggleSource(sourceKey: string, selected: boolean) {
    onSourceKeysChange(
      selected
        ? Array.from(new Set([...sourceKeys, sourceKey])).sort()
        : sourceKeys.filter((item) => item !== sourceKey),
    );
  }
  return (
    <FieldSet disabled={disabled}>
      <FieldLegend variant="label">信息来源</FieldLegend>
      <FieldDescription>
        选择你想持续关注的来源，保存后生效。也可以先保存，之后再配置。
      </FieldDescription>
      {sourceOptions.length > 0 ? (
        <FieldGroup className="gap-5">
          {sourceOptions.map((source) => {
            const unavailable =
              !source.selectable && !sourceKeys.includes(source.sourceKey);
            return (
              <FieldGroup key={source.sourceKey} className="gap-3">
                <Separator />
                <Field
                  orientation="horizontal"
                  data-disabled={disabled || unavailable}
                  data-invalid={Boolean(fieldErrors.source_keys)}
                >
                  <FieldContent>
                    <FieldLabel htmlFor={`source-${source.sourceKey}`}>
                      {source.displayName}
                    </FieldLabel>
                    <FieldDescription
                      id={`source-${source.sourceKey}-description`}
                    >
                      {source.reason}
                    </FieldDescription>
                  </FieldContent>
                  <Switch
                    id={`source-${source.sourceKey}`}
                    checked={sourceKeys.includes(source.sourceKey)}
                    onCheckedChange={(checked) =>
                      toggleSource(source.sourceKey, checked)
                    }
                    disabled={disabled || unavailable}
                    aria-invalid={Boolean(fieldErrors.source_keys)}
                    aria-describedby={`source-${source.sourceKey}-description`}
                  />
                </Field>
              </FieldGroup>
            );
          })}
        </FieldGroup>
      ) : (
        <FieldDescription>
          还没有可选来源。先到来源设置应用搜索预设，或保存后再设置。
        </FieldDescription>
      )}
      <Button asChild variant="link" className="w-fit px-0">
        <Link href="/sources">管理来源</Link>
      </Button>
    </FieldSet>
  );
}

const INTERVALS = [
  { value: 600, label: "每 10 分钟" },
  { value: 1800, label: "每 30 分钟" },
  { value: 3600, label: "每小时" },
  { value: 86400, label: "每天" },
];

type TopicAdvancedFieldsProps = {
  matchAll: string;
  onMatchAllChange: (value: string) => void;
  exclude: string;
  onExcludeChange: (value: string) => void;
  collectionIntervalSeconds: number;
  onCollectionIntervalSecondsChange: (value: number) => void;
  disabled: boolean;
  fieldErrors?: TopicFieldErrors;
};

export function TopicAdvancedFields({
  matchAll,
  onMatchAllChange,
  exclude,
  onExcludeChange,
  collectionIntervalSeconds,
  onCollectionIntervalSecondsChange,
  disabled,
  fieldErrors = {},
}: TopicAdvancedFieldsProps) {
  const [open, setOpen] = useState(
    Boolean(matchAll || exclude || collectionIntervalSeconds !== 3600),
  );
  const [customInterval, setCustomInterval] = useState(
    !INTERVALS.some((item) => item.value === collectionIntervalSeconds),
  );
  const hasError = Boolean(
    fieldErrors.match_all ||
    fieldErrors.exclude ||
    fieldErrors.collection_interval_seconds,
  );
  const expanded = open || hasError;
  return (
    <Collapsible open={expanded} onOpenChange={setOpen} disabled={disabled}>
      <CollapsibleTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="navigation"
          className="w-full justify-between"
          disabled={disabled}
        >
          进阶设置 <ChevronDownIcon data-icon="inline-end" />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent motion="height">
        <FieldSet className="pt-6" disabled={disabled || !expanded}>
          <FieldLegend className="sr-only">进阶设置字段</FieldLegend>
          <FieldGroup>
            <KeywordGroupField
              id="match-all"
              label="全部包含"
              description="每个关键词都需要出现；留空则不增加限制。"
              value={matchAll}
              onChange={onMatchAllChange}
              disabled={disabled}
              error={fieldErrors.match_all}
            />
            <KeywordGroupField
              id="exclude"
              label="排除"
              description="包含任意排除词的内容将被过滤。"
              value={exclude}
              onChange={onExcludeChange}
              disabled={disabled}
              error={fieldErrors.exclude}
            />
            <Field
              data-disabled={disabled}
              data-invalid={Boolean(fieldErrors.collection_interval_seconds)}
            >
              <FieldLabel htmlFor="collection-frequency">更新频率</FieldLabel>
              <Select
                value={
                  customInterval ? "custom" : String(collectionIntervalSeconds)
                }
                disabled={disabled}
                onValueChange={(value) => {
                  setCustomInterval(value === "custom");
                  if (value !== "custom")
                    onCollectionIntervalSecondsChange(Number(value));
                }}
              >
                <SelectTrigger
                  id="collection-frequency"
                  className="w-full"
                  aria-invalid={Boolean(
                    fieldErrors.collection_interval_seconds,
                  )}
                  aria-describedby="collection-frequency-description"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectLabel className="sr-only">更新频率</SelectLabel>
                    {INTERVALS.map((item) => (
                      <SelectItem key={item.value} value={String(item.value)}>
                        {item.label}
                      </SelectItem>
                    ))}
                    <SelectItem value="custom">自定义间隔</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
              <FieldDescription id="collection-frequency-description">
                实际采集也会遵循来源自身的频次限制。
              </FieldDescription>
            </Field>
            {customInterval ? (
              <Field
                data-disabled={disabled}
                data-invalid={Boolean(fieldErrors.collection_interval_seconds)}
              >
                <FieldLabel htmlFor="collection-interval">
                  采集频率（秒）
                </FieldLabel>
                <Input
                  id="collection-interval"
                  type="number"
                  min={600}
                  max={86400}
                  step={1}
                  value={
                    Number.isNaN(collectionIntervalSeconds)
                      ? ""
                      : collectionIntervalSeconds
                  }
                  onChange={(event) =>
                    onCollectionIntervalSecondsChange(
                      event.target.valueAsNumber,
                    )
                  }
                  disabled={disabled}
                  aria-invalid={Boolean(
                    fieldErrors.collection_interval_seconds,
                  )}
                  aria-describedby="collection-interval-description"
                />
                <FieldDescription id="collection-interval-description">
                  填写 600—86400 之间的整数秒。
                </FieldDescription>
              </Field>
            ) : null}
          </FieldGroup>
        </FieldSet>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function TopicReportFields({
  reportTime,
  onReportTimeChange,
  weeklyReportEnabled,
  onWeeklyReportEnabledChange,
  notificationTargetNames,
  onNotificationTargetNamesChange,
  disabled,
  error,
}: {
  reportTime: string;
  onReportTimeChange: (value: string) => void;
  weeklyReportEnabled: boolean;
  onWeeklyReportEnabledChange: (value: boolean) => void;
  notificationTargetNames: string[];
  onNotificationTargetNamesChange: (value: string[]) => void;
  disabled: boolean;
  error?: string;
}) {
  const [open, setOpen] = useState(false);
  const [subscription, setSubscription] =
    useState<HotKeyAPI.ReportEmailSubscriptionView | null>(null);
  const [failed, setFailed] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void getReportEmailSubscription({ signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) {
          setSubscription(value);
          setFailed(false);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setFailed(true);
          toast.error("邮件订阅读取失败，请重试。");
        }
      });
    return () => controller.abort();
  }, [open, reload]);
  const targetName = subscription?.target_name ?? "我的报告邮箱";
  const selected = notificationTargetNames.includes(targetName);
  const expanded = open || Boolean(error);
  return (
    <Collapsible open={expanded} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="navigation"
          className="w-full justify-between"
          disabled={disabled}
        >
          报告设置 <ChevronDownIcon data-icon="inline-end" />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent motion="height">
        <FieldSet className="pt-6" disabled={disabled || !expanded}>
          <FieldLegend className="sr-only">报告设置字段</FieldLegend>
          <FieldGroup>
            <Field data-disabled={disabled} data-invalid={Boolean(error)}>
              <FieldLabel htmlFor="report-time">每日报告时间</FieldLabel>
              <Input
                id="report-time"
                type="time"
                step="any"
                value={reportTime}
                onChange={(event) => onReportTimeChange(event.target.value)}
                disabled={disabled}
                required
                aria-invalid={Boolean(error)}
                aria-describedby="report-time-description"
              />
              <FieldDescription id="report-time-description">
                北京时间，汇总前一自然日的已获取材料。{error}
              </FieldDescription>
            </Field>
            <Field orientation="horizontal" data-disabled={disabled}>
              <FieldContent>
                <FieldLabel htmlFor="weekly-report">生成周报</FieldLabel>
                <FieldDescription>
                  每周一北京时间 08:00，汇总上一周的已获取材料。
                </FieldDescription>
              </FieldContent>
              <Switch
                id="weekly-report"
                checked={weeklyReportEnabled}
                onCheckedChange={onWeeklyReportEnabledChange}
                disabled={disabled}
              />
            </Field>
            <Field orientation="horizontal">
              <FieldContent>
                <FieldLabel htmlFor="topic-email-reports">
                  邮件发送日报和周报
                </FieldLabel>
                <FieldDescription>
                  {subscription?.enabled
                    ? `发送到 ${subscription.email}。`
                    : "先在账户设置中绑定邮箱并开启报告订阅。"}
                  {subscription?.enabled && !subscription.delivery_available
                    ? "平台发信服务尚未就绪，偏好仍可保存。"
                    : ""}
                </FieldDescription>
              </FieldContent>
              <Switch
                id="topic-email-reports"
                checked={selected}
                disabled={disabled || (!selected && !subscription?.enabled)}
                onCheckedChange={(value) =>
                  onNotificationTargetNamesChange(
                    value
                      ? [...new Set([...notificationTargetNames, targetName])]
                      : notificationTargetNames.filter(
                          (name) => name !== targetName,
                        ),
                  )
                }
              />
            </Field>
            {failed ? (
              <Button
                type="button"
                variant="outline"
                disabled={disabled}
                onClick={() => setReload((value) => value + 1)}
              >
                重试读取邮件订阅
              </Button>
            ) : !subscription && open ? (
              <Item role="status">
                <Spinner />
                正在读取邮件订阅…
              </Item>
            ) : null}
            <Button asChild variant="link" className="self-start">
              <Link href="/account">管理账户邮件订阅</Link>
            </Button>
            <FieldDescription>
              报告保留资料缺口。到期开始生成，完成后投递；个人资料仅本人可读。
            </FieldDescription>
          </FieldGroup>
        </FieldSet>
      </CollapsibleContent>
    </Collapsible>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDownIcon, RotateCcwIcon } from "lucide-react";
import { toast } from "sonner";

import { listPublicPlatformCatalog } from "@/api/laiyuannengli";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/request";

import { coverageTime } from "./coverage-window-table";

const STATUS_LABELS: Record<
  HotKeyAPI.PublicPlatformEntryView["status"],
  string
> = {
  candidate: "待验证",
  blocked: "暂不可执行",
  excluded: "首版排除",
  missing: "入口待确认",
};
const QUERY_LABELS: Record<
  HotKeyAPI.PublicPlatformEntryView["query_mode"],
  string
> = {
  author_feed: "作者订阅流",
  keyword_feed: "关键词结果订阅流",
  tag_feed: "标签 / 话题订阅流",
  hotlist: "热门榜单",
  comments_feed: "评论订阅流",
  unknown: "查询方式待确认",
};
const DOCUMENT_LABELS: Record<
  HotKeyAPI.PublicPlatformCapabilityView["documented_support"],
  string
> = {
  route_code: "有候选代码",
  unknown: "尚未验证",
  excluded: "首版排除",
};

function EntryDetails({ entry }: { entry: HotKeyAPI.PublicPlatformEntryView }) {
  const requirementGroups = [
    { label: "范围与限制", items: entry.limitations },
    { label: "启用前需要", items: entry.admission_requirements },
  ];
  return (
    <section
      aria-label={`${entry.display_name}能力详情`}
      className="flex flex-col gap-4"
    >
      <h4 className="font-medium">{entry.display_name}</h4>
      <dl className="grid gap-4 text-sm sm:grid-cols-2">
        {[
          ["目标对象", entry.object_scope],
          ["查询方式", QUERY_LABELS[entry.query_mode]],
          ["时间范围", entry.time_range],
          ["排序", entry.sort_order],
          ["分页", entry.pagination],
          ["执行准入", entry.execution_admitted ? "已准入" : "未通过"],
          ["真实试点", entry.trial_verified ? "已验证" : "未验证"],
          ["产品可用", entry.product_available ? "已可用" : "尚未上线"],
        ].map(([label, value]) => (
          <div key={label}>
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="mt-1 leading-6">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">资料声明</p>
        <ul className="grid gap-2 text-sm sm:grid-cols-2">
          {entry.capabilities.map((capability) => (
            <li
              key={capability.capability}
              className="flex items-start justify-between gap-3"
            >
              <span>{capability.display_name}</span>
              <span className="text-muted-foreground">
                {DOCUMENT_LABELS[capability.documented_support]}
              </span>
            </li>
          ))}
        </ul>
        <p className="text-muted-foreground text-sm leading-6">
          候选代码只说明存在技术入口，执行和产品可用仍须逐项验证。
        </p>
      </div>
      {requirementGroups.map(({ label, items }) => (
        <div key={label} className="flex flex-col gap-2">
          <p className="text-sm font-medium">{label}</p>
          <ul className="text-muted-foreground flex flex-col gap-2 text-sm leading-6">
            {items.map((value) => (
              <li key={value}>{value}</li>
            ))}
          </ul>
        </div>
      ))}
      <div className="text-muted-foreground flex flex-col gap-2 text-sm">
        <p>
          技术入口：<code>{entry.route_template ?? "尚未确认"}</code>
        </p>
        {entry.evidence_urls.map((url, index) => (
          <a
            key={url}
            href={url}
            target="_blank"
            rel="noreferrer"
            className="w-fit underline underline-offset-4"
          >
            查看固定源码依据 {index + 1}
          </a>
        ))}
      </div>
    </section>
  );
}

function Platform({
  platform,
}: {
  platform: HotKeyAPI.PublicPlatformCatalogView;
}) {
  return (
    <Collapsible>
      <Item className="items-start px-0">
        <ItemContent className="gap-4">
          <ItemTitle>
            <h3 className="text-lg font-medium">{platform.display_name}</h3>
          </ItemTitle>
          <ItemDescription className="line-clamp-none leading-6">
            {platform.scope_description}
          </ItemDescription>
          <ul className="flex flex-col gap-4">
            {platform.entries.map((entry) => (
              <li key={entry.entry_key} className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-medium">{entry.display_name}</span>
                  <Badge variant="outline">{STATUS_LABELS[entry.status]}</Badge>
                </div>
                <p className="text-muted-foreground text-sm leading-6">
                  {QUERY_LABELS[entry.query_mode]} · {entry.block_reason}
                </p>
                <dl className="text-muted-foreground flex flex-wrap gap-x-5 gap-y-2 text-sm">
                  <div>
                    <dt className="inline">供应商费用上限：</dt>
                    <dd className="inline">{entry.supplier_fee_cap_micros}</dd>
                    <span>
                      {entry.fee_status === "disallowed"
                        ? "（本轮禁止收费路径）"
                        : "（入口零费用待核实）"}
                    </span>
                  </div>
                  <div>
                    <dt className="inline">最近持久成功：</dt>
                    <dd className="inline">
                      {entry.last_persisted_success_at
                        ? coverageTime(entry.last_persisted_success_at)
                        : "尚无记录"}
                    </dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        </ItemContent>
        <ItemActions>
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              aria-label={`查看${platform.display_name}入口详情`}
            >
              查看详情
              <ChevronDownIcon data-icon="inline-end" />
            </Button>
          </CollapsibleTrigger>
        </ItemActions>
      </Item>
      <CollapsibleContent className="flex flex-col gap-6 pt-4 pb-6">
        <p className="text-muted-foreground text-sm leading-6">
          资料核验日期：{platform.inspected_at}。固定源码版本：
          <code className="break-all">{platform.inspected_revision}</code>。
          本记录未验证当前运行服务或平台采集结果。
        </p>
        {platform.entries.map((entry) => (
          <EntryDetails key={entry.entry_key} entry={entry} />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

export function PublicPlatformCatalog() {
  const [platforms, setPlatforms] = useState<
    HotKeyAPI.PublicPlatformCatalogView[] | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [readFailed, setReadFailed] = useState(false);
  const controller = useRef<AbortController | null>(null);

  const read = useCallback(
    (current: AbortController) =>
      listPublicPlatformCatalog({ signal: current.signal })
        .then((page) => {
          if (!current.signal.aborted) setPlatforms(page.items);
        })
        .catch((failure: unknown) => {
          if (current.signal.aborted) return;
          if (
            failure instanceof ApiRequestError &&
            failure.kind === "cancelled"
          )
            return;
          setReadFailed(true);
          toast.error(
            failure instanceof ApiRequestError
              ? `${failure.message}${failure.requestId ? ` 请求编号：${failure.requestId}` : ""}`
              : "平台目录加载失败，请重试。",
          );
        })
        .finally(() => {
          if (!current.signal.aborted) setLoading(false);
        }),
    [],
  );

  const refresh = useCallback(async () => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setLoading(true);
    setReadFailed(false);
    await read(current);
  }, [read]);

  useEffect(() => {
    const current = new AbortController();
    controller.current = current;
    void read(current);
    return () => controller.current?.abort();
  }, [read]);

  return (
    <section
      aria-labelledby="public-platform-heading"
      className="flex flex-col gap-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-2">
          <h2 id="public-platform-heading" className="text-xl font-medium">
            七平台免费入口
          </h2>
          <p className="text-muted-foreground max-w-2xl text-sm leading-6">
            查看各平台能研究的入口、范围和阻断原因。候选入口尚不可执行，
            热榜、作者订阅和关键词结果分别验证。本机资源仍有成本。
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={loading}
          onClick={() => void refresh()}
        >
          <RotateCcwIcon data-icon="inline-start" />
          刷新平台目录
        </Button>
      </div>
      {readFailed ? (
        <Alert variant="destructive">
          <AlertTitle>暂时无法读取平台目录</AlertTitle>
          <AlertDescription>
            {platforms
              ? "当前为上次读取的资料，请刷新后再核对。"
              : "请重新加载平台目录。"}
            <Button
              variant="outline"
              size="sm"
              disabled={loading}
              onClick={() => void refresh()}
            >
              重新加载平台目录
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      {platforms === null && loading ? (
        <div aria-label="正在读取平台目录" className="flex flex-col gap-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : null}
      {platforms?.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>平台目录暂为空</EmptyTitle>
            <EmptyDescription>
              尚未取得候选资料，请重新加载；这不表示平台已验证无内容。
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}
      <ItemGroup className="gap-8">
        {platforms?.map((platform, index) => (
          <div key={platform.platform_key}>
            {index > 0 ? <Separator className="mb-8" /> : null}
            <Platform platform={platform} />
          </div>
        ))}
      </ItemGroup>
    </section>
  );
}

"use client";
import * as UI from "@/components/ui/content";

import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";

import { toast } from "sonner";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowLeftIcon,
  ChevronDownIcon,
  ExternalLinkIcon,
  RotateCcwIcon,
} from "lucide-react";

import { getContentRecord } from "@/api/zuopinziliao";
import { AnnotationPanel } from "@/app/content/[contentId]/components/annotation-panel";
import { CommentThreadList } from "@/app/content/[contentId]/components/comment-thread-list";
import { ContentSources } from "@/app/content/[contentId]/components/content-sources";
import {
  contentOriginLabel,
  contentScopeLabel,
  contentScopeNotice,
  contentSourceLabel,
  formatMetric,
  formatTime,
  hasUnknownMetrics,
  METRIC_LABELS,
  relationTypeLabel,
  scanKindLabel,
  safeExternalHref,
  truncationReasonLabel,
  visibilityBasisLabel,
  visibilityStatusLabel,
  visibilityStatusNotice,
} from "@/app/content/components/content-presenters";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageState } from "@/components/system/page-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/request";
import { PrivateExport } from "@/components/reports/private-export";

type ContentDetailProps = { contentId: string };

type DetailState =
  | { status: "loading" }
  | { status: "ready"; content: HotKeyAPI.ContentRecordDetailView }
  | { status: "not-found" }
  | { status: "error"; message: string; requestId?: string };

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <UI.Content className="min-w-0">
      <UI.Content as="dt" className="text-muted-foreground text-sm">
        {label}
      </UI.Content>
      <UI.Content as="dd" className="mt-1 font-medium break-words">
        {value}
      </UI.Content>
    </UI.Content>
  );
}

function ContentVersionSection({
  version,
}: {
  version: HotKeyAPI.ContentVersionView | null;
}) {
  if (version === null) {
    return (
      <UI.Content
        as="section"
        aria-labelledby="content-heading"
        className="mt-10"
      >
        <UI.Heading
          level={2}
          id="content-heading"
          className="text-xl font-medium"
        >
          正文与上下文
        </UI.Heading>
        <UI.Content className="mt-6">
          <UI.Text className="font-medium">未取得正文</UI.Text>
          <Empty className="mt-2 leading-6">
            <EmptyHeader>
              <EmptyDescription>
                当前观察没有可用正文版本；未知不等于空正文。
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        </UI.Content>
      </UI.Content>
    );
  }

  const notice = contentScopeNotice(version.text_scope, version.text_origin);
  return (
    <UI.Content
      as="section"
      aria-labelledby="content-heading"
      className="mt-10"
    >
      <UI.Heading
        level={2}
        id="content-heading"
        className="text-xl font-medium"
      >
        正文与上下文
      </UI.Heading>
      <UI.Content className="mt-6">
        <UI.Content className="flex flex-wrap gap-2">
          <Badge variant="secondary">
            {contentScopeLabel(version.text_scope, version.text_origin)}
          </Badge>
          <Badge variant="outline">
            {contentOriginLabel(version.text_origin)}
          </Badge>
        </UI.Content>
        {notice ? (
          <UI.Text className="border-border text-muted-foreground mt-4 border-l-2 pl-4 text-sm leading-6">
            {notice}
          </UI.Text>
        ) : null}
        {version.title ? (
          <UI.Heading
            level={3}
            className="mt-6 text-lg font-medium break-words whitespace-pre-wrap"
          >
            {version.title}
          </UI.Heading>
        ) : null}
        {version.body ? (
          <UI.Text className="mt-4 leading-7 break-words whitespace-pre-wrap">
            {version.body}
          </UI.Text>
        ) : null}
        {version.truncation_reason ? (
          <UI.Text className="text-muted-foreground mt-4 text-sm">
            截断原因：{truncationReasonLabel(version.truncation_reason)}
          </UI.Text>
        ) : null}
        {version.text_origin_ref ? (
          <Collapsible className="mt-4">
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="sm">
                提取依据
                <ChevronDownIcon data-icon="inline-end" />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="text-muted-foreground mt-2 font-mono text-xs break-all">
              {version.text_origin_ref}
            </CollapsibleContent>
          </Collapsible>
        ) : null}
      </UI.Content>
      {version.relations.length > 0 ? (
        <UI.Content className="mt-6 grid gap-6 sm:grid-cols-2">
          {version.relations.map((relation) => (
            <UI.Content
              as="article"
              key={`${relation.relation_type}:${relation.target_native_scope ?? ""}:${relation.target_external_id}`}
              className="py-4"
            >
              <Badge variant="outline">
                {relationTypeLabel(relation.relation_type)}
              </Badge>
              <UI.Text className="mt-3 font-mono text-sm break-all">
                {relation.target_external_id}
              </UI.Text>
              <UI.Text className="text-muted-foreground mt-2 text-xs break-all">
                目标作者：
                {relation.target_author_external_id ?? "未知"}
              </UI.Text>
              {relation.target_content_id ? (
                <Link
                  className="mt-3 inline-flex text-sm underline underline-offset-4"
                  href={`/content/${relation.target_content_id}`}
                >
                  查看已获取的目标作品
                </Link>
              ) : (
                <UI.Text className="text-muted-foreground mt-3 text-sm">
                  目标作品未获取或当前不可读。
                </UI.Text>
              )}
            </UI.Content>
          ))}
        </UI.Content>
      ) : null}
    </UI.Content>
  );
}

function visibilityBadgeVariant(
  status: HotKeyAPI.ContentVisibilityStatus,
): "secondary" | "destructive" | "outline" {
  if (status === "visible") {
    return "secondary";
  }
  return status === "deleted" || status === "restricted"
    ? "destructive"
    : "outline";
}

function VisibilitySummary({
  visibility,
}: {
  visibility: HotKeyAPI.ContentVisibilityView | null;
}) {
  return (
    <UI.Content
      as="section"
      aria-labelledby="visibility-heading"
      className="mt-8"
    >
      <UI.Heading
        level={2}
        id="visibility-heading"
        className="text-xl font-medium"
      >
        当前来源状态
      </UI.Heading>
      <UI.Content className="mt-6">
        {visibility ? (
          <>
            <UI.Content className="flex flex-wrap items-center gap-2">
              <Badge variant={visibilityBadgeVariant(visibility.status)}>
                {visibilityStatusLabel(visibility.status)}
              </Badge>
              <UI.Text as="span" className="text-muted-foreground text-xs">
                观察于 {formatTime(visibility.observed_at)}
              </UI.Text>
            </UI.Content>
            <UI.Text className="mt-3 text-sm leading-6">
              {visibilityStatusNotice(visibility.status)}
            </UI.Text>
          </>
        ) : (
          <Empty className="leading-6">
            <EmptyHeader>
              <EmptyDescription>
                尚无独立来源状态观察，不能据此判断作品当前是否可见。
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
      </UI.Content>
    </UI.Content>
  );
}

function VersionHistory({
  history,
}: {
  history: HotKeyAPI.ContentVersionHistoryView[];
}) {
  return (
    <UI.Content
      as="section"
      aria-labelledby="version-history-heading"
      className="mt-10"
    >
      <UI.Heading
        level={2}
        id="version-history-heading"
        className="text-xl font-medium"
      >
        正文版本历史
      </UI.Heading>
      <UI.Text className="text-muted-foreground mt-2 text-sm leading-6">
        按来源观察时间排序；稳定版本 ID 可供后续分析引用。
      </UI.Text>
      <UI.Content className="mt-6 flex flex-col gap-6">
        {history.map((entry) => (
          <UI.Content
            as="article"
            key={entry.content_version.id}
            className="py-4"
          >
            <UI.Content className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">
                {contentScopeLabel(
                  entry.content_version.text_scope,
                  entry.content_version.text_origin,
                )}
              </Badge>
              <Badge variant="outline">
                {contentOriginLabel(entry.content_version.text_origin)}
              </Badge>
              <UI.Text as="span" className="text-muted-foreground text-xs">
                {entry.observation_count} 次观察
              </UI.Text>
            </UI.Content>
            <UI.Text className="mt-3 font-mono text-xs break-all">
              {entry.content_version.id}
            </UI.Text>
            <UI.Text className="text-muted-foreground mt-2 text-xs leading-5">
              首次 {formatTime(entry.first_observed_at)} · 最近{" "}
              {formatTime(entry.last_observed_at)}
            </UI.Text>
            {(entry.content_version.title ?? entry.content_version.body) ? (
              <UI.Text className="mt-3 line-clamp-3 text-sm break-words whitespace-pre-wrap">
                {entry.content_version.title ?? entry.content_version.body}
              </UI.Text>
            ) : (
              <UI.Text className="text-muted-foreground mt-3 text-sm">
                仅媒体，无文本
              </UI.Text>
            )}
          </UI.Content>
        ))}
      </UI.Content>
    </UI.Content>
  );
}

function VisibilityHistory({
  history,
}: {
  history: HotKeyAPI.ContentVisibilityView[];
}) {
  return (
    <UI.Content
      as="section"
      aria-labelledby="visibility-history-heading"
      className="mt-10"
    >
      <UI.Heading
        level={2}
        id="visibility-history-heading"
        className="text-xl font-medium"
      >
        来源状态历史
      </UI.Heading>
      <UI.Content className="mt-6 grid gap-6 sm:grid-cols-2">
        {history.map((entry) => (
          <UI.Content as="article" key={entry.id} className="py-4">
            <Badge variant={visibilityBadgeVariant(entry.status)}>
              {visibilityStatusLabel(entry.status)}
            </Badge>
            <UI.Text className="mt-3 text-sm">
              {visibilityBasisLabel(entry.basis)}
            </UI.Text>
            <UI.Text className="text-muted-foreground mt-2 text-xs">
              观察于 {formatTime(entry.observed_at)}
            </UI.Text>
          </UI.Content>
        ))}
      </UI.Content>
    </UI.Content>
  );
}

export function ContentDetail({ contentId }: ContentDetailProps) {
  const [state, setState] = useState<DetailState>({ status: "loading" });
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void getContentRecord(
      { content_id: contentId },
      { signal: controller.signal },
    )
      .then((content) => {
        if (!controller.signal.aborted) {
          setState({ status: "ready", content });
        }
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (controller.signal.aborted) {
          return;
        }
        if (
          error instanceof ApiRequestError &&
          error.code === "resource_not_found"
        ) {
          setState({ status: "not-found" });
        } else {
          toast.error(
            error instanceof ApiRequestError
              ? error.message
              : "作品资料加载失败，请稍后重试。",
            {
              description:
                error instanceof ApiRequestError && error.requestId
                  ? `请求编号：${error.requestId}`
                  : undefined,
            },
          );
          setState(
            error instanceof ApiRequestError
              ? {
                  status: "error",
                  message: error.message,
                  requestId: error.requestId,
                }
              : { status: "error", message: "作品资料加载失败，请稍后重试。" },
          );
        }
      });
    return () => {
      controller.abort();
    };
  }, [contentId, retryToken]);

  if (state.status === "loading") {
    return (
      <PageState
        state="loading"
        loadingLayout="detail"
        eyebrow="作品资料"
        title="正在读取作品"
        description="正在读取已保存的作品身份、最近观察与发现依据。"
      />
    );
  }

  if (state.status === "not-found") {
    return (
      <PageState
        state="empty"
        eyebrow="作品不可用"
        title="没有找到这个作品"
        description="作品不存在或已不可读。"
        action={
          <Button asChild variant="secondary">
            <Link href="/content">
              <ArrowLeftIcon data-icon="inline-start" />
              返回作品列表
            </Link>
          </Button>
        }
      />
    );
  }

  if (state.status === "error") {
    return (
      <PageState
        state="error"
        eyebrow="加载失败"
        title="暂时无法读取作品"
        description="请重新加载作品资料。"
        action={
          <Button
            type="button"
            onClick={() => {
              setState({ status: "loading" });
              setRetryToken((value) => value + 1);
            }}
          >
            <RotateCcwIcon data-icon="inline-start" />
            重新加载
          </Button>
        }
      />
    );
  }

  const { content } = state;
  const observation = content.latest_observation;
  const canonicalHref = safeExternalHref(observation.canonical_url);

  const title = observation.content_version?.title ?? content.external_id;
  return (
    <UI.Content>
      <Button asChild variant="ghost" size="sm">
        <Link href="/content">
          <ArrowLeftIcon data-icon="inline-start" />
          返回作品列表
        </Link>
      </Button>
      <UI.Heading
        level={1}
        className="mt-8 text-3xl font-normal tracking-tight break-words sm:text-4xl"
      >
        {title}
      </UI.Heading>
      <UI.Content className="text-muted-foreground mt-4 flex flex-wrap items-center gap-3 text-sm">
        <UI.Text as="span">
          {contentSourceLabel(content.source_key, content.source_name)}
        </UI.Text>
        <UI.Text as="span">
          {formatTime(observation.published_at ?? observation.observed_at)}
        </UI.Text>
        {hasUnknownMetrics(observation.metrics) ? (
          <UI.Text as="span">部分指标未知</UI.Text>
        ) : null}
        {canonicalHref ? (
          <Button asChild variant="ghost" size="sm">
            <UI.TextLink href={canonicalHref} target="_blank" rel="noreferrer">
              打开原文
              <ExternalLinkIcon data-icon="inline-end" />
            </UI.TextLink>
          </Button>
        ) : (
          <UI.Text as="span">原文链接未知</UI.Text>
        )}
      </UI.Content>
      <UI.Content
        as="section"
        className="mt-6 space-y-3"
        aria-label="私人内容导出"
      >
        <UI.Heading level={2} className="text-lg font-medium">
          导出这版材料
        </UI.Heading>
        <UI.Text className="text-muted-foreground text-sm">
          保留当前版本、来源与实际文本范围；下载需有效的文件导出许可。
        </UI.Text>
        <PrivateExport
          target={{
            kind: "content",
            contentVersionIds: observation.content_version
              ? [observation.content_version.id]
              : [],
          }}
        />
      </UI.Content>
      <Tabs defaultValue="body" className="mt-10 min-w-0">
        <TabsList className="max-w-full">
          <TabsTrigger value="body">正文</TabsTrigger>
          {content.object_type === "post" ? (
            <TabsTrigger value="comments">评论</TabsTrigger>
          ) : null}
          <TabsTrigger value="analysis">分析</TabsTrigger>
          <TabsTrigger value="records">记录</TabsTrigger>
        </TabsList>
        <TabsContent value="body">
          <ContentVersionSection
            version={observation.content_version ?? null}
          />
          <VisibilitySummary visibility={content.current_visibility} />
        </TabsContent>
        {content.object_type === "post" ? (
          <TabsContent value="comments">
            <CommentThreadList
              key={`comments-${content.id}`}
              postId={content.id}
            />
          </TabsContent>
        ) : null}
        <TabsContent value="analysis">
          <AnnotationPanel key={`annotation-${content.id}`} content={content} />
        </TabsContent>
        <TabsContent value="records">
          <UI.Text className="text-muted-foreground mt-8 text-sm">
            读取已保存的观察，不会刷新来源。未知指标保留为未知。
          </UI.Text>
          <UI.Content
            as="section"
            aria-labelledby="identity-heading"
            className="mt-10"
          >
            <UI.Heading
              level={2}
              id="identity-heading"
              className="text-xl font-medium"
            >
              作品身份
            </UI.Heading>
            <UI.Content as="dl" className="mt-6 grid gap-6 sm:grid-cols-2">
              <DetailItem
                label="当前读取来源"
                value={contentSourceLabel(
                  content.source_key,
                  content.source_name,
                )}
              />
              <DetailItem label="对象类型" value={content.object_type} />
              <DetailItem
                label="原生作用域"
                value={content.native_scope ?? "未知"}
              />
              <DetailItem
                label="作者原生 ID"
                value={observation.author_external_id ?? "未知"}
              />
              <DetailItem
                label="发布时间"
                value={formatTime(observation.published_at)}
              />
              <DetailItem
                label="观察时间"
                value={formatTime(observation.observed_at)}
              />
            </UI.Content>
          </UI.Content>
          <ContentSources content={content} />
          <VersionHistory history={content.version_history} />
          <VisibilityHistory history={content.visibility_history} />
          <UI.Content
            as="section"
            aria-labelledby="metrics-heading"
            className="mt-10"
          >
            <UI.Heading
              level={2}
              id="metrics-heading"
              className="text-xl font-medium"
            >
              最近指标观察
            </UI.Heading>
            <UI.Content
              as="dl"
              className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3"
            >
              {METRIC_LABELS.map(([key, label]) => (
                <UI.Content key={key} className="py-4">
                  <UI.Content as="dt" className="text-muted-foreground text-sm">
                    {label}
                  </UI.Content>
                  <UI.Content
                    as="dd"
                    className="mt-2 text-2xl font-semibold tabular-nums"
                  >
                    {formatMetric(observation.metrics[key])}
                  </UI.Content>
                </UI.Content>
              ))}
            </UI.Content>
          </UI.Content>
          <UI.Content
            as="section"
            aria-labelledby="discoveries-heading"
            className="mt-10"
          >
            <UI.Heading
              level={2}
              id="discoveries-heading"
              className="text-xl font-medium"
            >
              发现依据
            </UI.Heading>
            <UI.Text className="text-muted-foreground mt-2 text-sm">
              同一作品可由多个任务发现；以下仅显示仍有可读观察的任务关系。
            </UI.Text>
            <UI.Content className="mt-6 flex flex-col gap-6">
              {content.discoveries.map((discovery) => (
                <UI.Content
                  as="article"
                  key={discovery.job_id}
                  className="py-4"
                >
                  <UI.Content className="flex flex-wrap items-start justify-between gap-3">
                    <UI.Content className="min-w-0">
                      <UI.Heading level={3} className="font-medium break-words">
                        {discovery.configuration_ref}
                      </UI.Heading>
                      <UI.Text className="text-muted-foreground mt-1 text-xs">
                        配置版本 v{discovery.configuration_version}
                      </UI.Text>
                      <UI.Text className="text-muted-foreground mt-1 text-xs">
                        {scanKindLabel(discovery.scan_kind)}
                      </UI.Text>
                    </UI.Content>
                    <Badge variant="outline">
                      {formatTime(discovery.first_observed_at)}
                    </Badge>
                  </UI.Content>
                  <Button asChild variant="ghost" size="sm" className="mt-3">
                    <Link href={`/jobs/${discovery.job_id}`}>查看采集任务</Link>
                  </Button>
                </UI.Content>
              ))}
            </UI.Content>
          </UI.Content>
        </TabsContent>
      </Tabs>
    </UI.Content>
  );
}

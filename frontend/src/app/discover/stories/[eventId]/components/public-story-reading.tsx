"use client";

import { useEffect, useRef, useState } from "react";
import { getPublicStoryDevelopments } from "@/api/gongkaifabu";
import * as UI from "@/components/ui/content";
import { Button } from "@/components/ui/button";
import { ItemGroup } from "@/components/ui/item";
import { Skeleton } from "@/components/ui/skeleton";
import { EditionCopyLink } from "@/components/publication/edition-copy-link";
import {
  ObservationGap,
  SignalNotice,
  SentimentLegend,
} from "@/components/ui/signal";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  EventColumns,
  EventEmpty,
  EventHeader,
  EventSectionFailure,
  EventSources,
  EventTimeline,
  FactSummary,
} from "@/components/events/event-reading";
import {
  eventTime,
  publicSources,
  sourceTimeline,
} from "@/components/events/reading-model";
import { ApiRequestError } from "@/request";

type DevelopmentsState =
  | { status: "loading" }
  | { status: "error"; error: unknown }
  | { status: "ready"; page: HotKeyAPI.PublicDevelopmentsPage };

export function PublicStoryReading({
  story,
}: {
  story: HotKeyAPI.PublicStoryView;
}) {
  const [state, setState] = useState<DevelopmentsState>({ status: "loading" });
  const [retry, setRetry] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const current = new AbortController();
    controller.current = current;
    void getPublicStoryDevelopments(
      { event_id: story.id, limit: 20, window: "7d" },
      { signal: current.signal },
    )
      .then((page) => {
        if (!current.signal.aborted) setState({ status: "ready", page });
      })
      .catch((error: unknown) => {
        if (
          !current.signal.aborted &&
          !(error instanceof ApiRequestError && error.kind === "cancelled")
        )
          setState({ status: "error", error });
      });
    return () => current.abort();
  }, [story.id, retry]);

  async function more() {
    if (state.status !== "ready" || !state.page.next_cursor || loadingMore)
      return;
    const signal = controller.current?.signal;
    setLoadingMore(true);
    try {
      const page = await getPublicStoryDevelopments(
        {
          event_id: story.id,
          limit: 20,
          window: "7d",
          cursor: state.page.next_cursor,
          revision: state.page.revision,
        },
        { signal },
      );
      if (!signal?.aborted)
        setState({
          status: "ready",
          page: {
            ...page,
            developments: [
              ...new Map(
                [...state.page.developments, ...page.developments].map(
                  (entry) => [entry.fact_id, entry],
                ),
              ).values(),
            ],
          },
        });
    } catch (error: unknown) {
      // Drop the old development projection after a failure, including stale
      // cursor / permission changes; retry always starts a fresh snapshot.
      if (
        !signal?.aborted &&
        !(error instanceof ApiRequestError && error.kind === "cancelled")
      )
        setState({ status: "error", error });
    } finally {
      if (!signal?.aborted) setLoadingMore(false);
    }
  }
  const developments = state.status === "ready" ? state.page.developments : [];
  const sources = publicSources([
    ...story.reports,
    ...developments.map((entry) => entry.representative),
  ]);
  return (
    <UI.Content className="flex min-w-0 flex-col gap-8">
      <EventHeader
        title={story.title}
        firstSeenAt={story.first_seen_at}
        sourceCount={
          new Set(
            [
              ...story.reports,
              ...developments.map((entry) => entry.representative),
            ].map((item) => item.source.key),
          ).size
        }
        heat={story.heat}
        revision={story.revision}
        phase={story.phase}
        href="/discover/stories"
        updatedAt={story.attention?.last_source_time}
        actions={
          <UI.Content layout="row">
            <Button variant="secondary" disabled title="事件关注暂未开放">
              关注
            </Button>
            <Button variant="secondary" disabled title="事件收藏暂未开放">
              收藏
            </Button>
            <EditionCopyLink href={`/discover/stories/${story.id}`} />
          </UI.Content>
        }
      />

      <EventColumns
        aside={
          <>
            <UI.Content as="section" layout="stack">
              <UI.Heading>大家怎么看</UI.Heading>
              <UI.Text size="xs" tone="muted">
                暂无公开评论样本
              </UI.Text>
              <ObservationGap compact>情感占比暂无数据</ObservationGap>
              <SentimentLegend />
            </UI.Content>
            <SignalNotice title="负面突增提醒">
              <UI.Text size="sm" tone="muted">
                暂无有效的公开情感观测。
              </UI.Text>
            </SignalNotice>
            <UI.Content layout="stack">
              <UI.Heading>代表观点</UI.Heading>
              <ToggleGroup
                type="single"
                size="default"
                value="all"
                aria-label="观点立场"
              >
                <ToggleGroupItem value="all">全部</ToggleGroupItem>
                <ToggleGroupItem value="negative" disabled>
                  担忧
                </ToggleGroupItem>
                <ToggleGroupItem value="neutral" disabled>
                  中立
                </ToggleGroupItem>
                <ToggleGroupItem value="positive" disabled>
                  支持
                </ToggleGroupItem>
              </ToggleGroup>
              <EventEmpty>公开资料暂未提供代表评论。</EventEmpty>
            </UI.Content>
            <UI.Content as="section" layout="stack">
              <UI.Heading>平台分布</UI.Heading>
              <UI.Text size="xs" tone="muted">
                按当前已加载的公开报道统计
              </UI.Text>
              {[...new Set(sources.map((source) => source.source))].map(
                (name) => (
                  <UI.Content
                    key={name}
                    className="flex items-center justify-between gap-4 border-b py-3"
                  >
                    <UI.Text size="sm">{name}</UI.Text>
                    <UI.Text size="sm" tone="muted">
                      <UI.InlineCode>
                        {
                          sources.filter((source) => source.source === name)
                            .length
                        }
                      </UI.InlineCode>{" "}
                      篇
                    </UI.Text>
                  </UI.Content>
                ),
              )}
            </UI.Content>
          </>
        }
      >
        <UI.Content as="section" className="flex flex-col gap-4">
          <UI.Heading>发生了什么</UI.Heading>
          <UI.Text className="whitespace-pre-wrap">{story.summary}</UI.Text>
          {story.latest_progress ? (
            <>
              <UI.Heading level={3}>最新进展</UI.Heading>
              <UI.Text className="whitespace-pre-wrap">
                {story.latest_progress}
              </UI.Text>
            </>
          ) : null}
        </UI.Content>
        <UI.Content as="section" className="flex flex-col gap-4">
          <UI.Heading>热度与负面占比</UI.Heading>
          <ObservationGap>
            暂无公开历史曲线与负面占比，不能由单次热度推算趋势。
          </ObservationGap>
          {story.attention ? (
            <UI.Text size="sm" tone="muted">
              当前热度窗口{" "}
              <UI.InlineCode>
                {eventTime(story.attention.window_end)}
              </UI.InlineCode>{" "}
              ·{" "}
              <UI.InlineCode>{story.attention.participant_count}</UI.InlineCode>{" "}
              个独立参与者。
              {story.attention.complete ? "" : "部分来源尚未完成及时采集。"}
            </UI.Text>
          ) : null}
        </UI.Content>
        <UI.Content
          as="section"
          className="flex flex-col gap-4"
          aria-labelledby="public-event-facts-heading"
        >
          <UI.Heading id="public-event-facts-heading">事实与进展</UI.Heading>
          <UI.Text tone="muted" size="sm">
            最近 7 天可公开的事实与进展；引用指向对应的代表报道。
          </UI.Text>
          {state.status === "error" ? (
            <EventSectionFailure
              title="无法读取公开事实与进展"
              error={state.error}
              retry={() => {
                setState({ status: "loading" });
                setRetry((value) => value + 1);
              }}
            />
          ) : state.status === "loading" ? (
            <Skeleton
              aria-label="正在读取公开事实与进展"
              className="h-24 w-full motion-reduce:animate-none"
            />
          ) : !developments.length ? (
            <EventEmpty>当前窗口尚无可公开的事实与进展。</EventEmpty>
          ) : (
            <ItemGroup>
              {developments.map((entry) => (
                <FactSummary
                  key={entry.fact_id}
                  title={entry.title}
                  sources={sources.filter(
                    (source) => source.id === entry.representative.id,
                  )}
                >
                  <UI.Text size="sm" tone="muted">
                    <UI.InlineCode>{eventTime(entry.anchor_at)}</UI.InlineCode>{" "}
                    · <UI.InlineCode>{entry.report_count}</UI.InlineCode>{" "}
                    篇公开报道
                  </UI.Text>
                </FactSummary>
              ))}
            </ItemGroup>
          )}
          {state.status === "ready" && state.page.next_cursor ? (
            <Button
              variant="outline"
              disabled={loadingMore}
              onClick={() => void more()}
            >
              {loadingMore ? "正在读取更多进展…" : "加载更多事实与进展"}
            </Button>
          ) : null}
        </UI.Content>
        <EventTimeline
          entries={sourceTimeline(sources)}
          description="按当前已加载的公开报道时间排列。"
        />
        <EventSources sources={sources} />
      </EventColumns>
    </UI.Content>
  );
}

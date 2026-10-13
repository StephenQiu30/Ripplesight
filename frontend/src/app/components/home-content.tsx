"use client";

import { PageHeader } from "@/components/system/page-header";

import { AuthLink as Link } from "@/components/auth/auth-link";
import { useEffect, useId, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { SearchIcon, ArrowUpRightIcon } from "lucide-react";
import { HomeStoryFeed } from "./home-feed";
import {
  homeUpdatedAt,
  homeCategories,
  readableHomeReading,
  homeRisingStories,
  type HomeReading,
} from "./home-format";
import { Button } from "@/components/ui/button";
import {
  Content,
  Heading,
  Text,
  InlineCode,
  Form,
} from "@/components/ui/content";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { SentimentLegend } from "@/components/ui/signal";
import { PageState } from "@/components/system/page-state";
import { LoadingSignal } from "@/components/system/global-loading";
import { useLayoutScrollContainer } from "@/layout/basic-layout";
import { ReportSentiment } from "@/components/publication/report-sentiment";
import { heatTrendLabel } from "@/components/publication/heat-history";
import { PlatformTrends } from "@/components/publication/platform-trends";
import { NegativeSurge } from "@/components/publication/negative-surge";
import { publicationTime } from "@/components/publication/reading-format";

export type { HomeReading } from "./home-format";
const emptyReading: HomeReading = {
  stories: [],
  editions: [],
  unavailable: [],
};

export function HomeContent({
  reading = emptyReading,
  category = "all",
}: {
  reading?: HomeReading;
  category?: string;
}) {
  const router = useRouter();
  const scroll = useLayoutScrollContainer();
  const searchId = useId();
  const [visibleCount, setVisibleCount] = useState(6);
  const [isPending, startTransition] = useTransition();
  const refresh = () => startTransition(() => router.refresh());
  reading = readableHomeReading(reading);
  useEffect(() => {
    scroll?.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [scroll, category]);
  const stories =
    category === "all"
      ? reading.stories
      : reading.stories.filter((story) =>
          story.reports.some(
            (item) =>
              item.category === category || item.tags.includes(category),
          ),
        );
  const observedAt = reading.observedAt ?? "";
  const updatedAt = homeUpdatedAt(reading);
  const rising = homeRisingStories(reading.stories);
  const denied = [401, 403].includes(reading.failures?.stories?.status ?? 0);
  const storiesUnavailable =
    reading.unavailable.includes("stories") ||
    Boolean(reading.failures?.stories);
  const editionsUnavailable =
    reading.unavailable.includes("editions") ||
    Boolean(reading.failures?.editions);
  const emptyCategory = category !== "all" && reading.stories.length > 0;
  const notice = (
    <Content layout="stack" className="gap-8">
      <NegativeSurge
        surge={reading.negativeSurge}
        failure={
          storiesUnavailable ? (reading.failures?.stories ?? {}) : undefined
        }
      />
      <ReportSentiment sentiment={reading.sentiment} />
    </Content>
  );
  return (
    <Content layout="stack" className="gap-6 md:gap-8" aria-busy={isPending}>
      <LoadingSignal active={isPending} />
      <PageHeader
        titleAppearance="home"
        title="今日 AI 热点"
        description={
          updatedAt ? (
            <InlineCode>更新于 {publicationTime(updatedAt)}</InlineCode>
          ) : undefined
        }
        actions={
          <Content className="flex w-full min-w-0 flex-wrap items-center gap-2 @min-[40rem]/page:w-auto">
            <Form
              action="/discover"
              role="search"
              aria-label="搜索事件、主题或来源"
              className="min-w-0 flex-1 @min-[40rem]/page:w-70"
            >
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor={searchId} className="sr-only">
                    搜索事件、主题或来源
                  </FieldLabel>
                  <InputGroup>
                    <InputGroupAddon>
                      <SearchIcon />
                    </InputGroupAddon>
                    <InputGroupInput
                      id={searchId}
                      name="q"
                      type="search"
                      maxLength={200}
                      placeholder="搜索事件、主题或来源"
                    />
                  </InputGroup>
                </Field>
              </FieldGroup>
            </Form>
            <Button asChild>
              <Link href="/feed/daily.xml">订阅 RSS</Link>
            </Button>
          </Content>
        }
      />
      <Content
        as="dl"
        aria-label="今日概览"
        className="grid grid-cols-2 gap-x-4 gap-y-4 border-y py-4 md:gap-x-8 md:py-5 @min-[40rem]/page:grid-cols-4"
      >
        {(
          [
            ["公开事件", reading.overview?.total_events],
            ["24小时新识别", reading.overview?.new_events_24h],
            ["旧事件进展归入", reading.overview?.updated_events_24h],
            ["覆盖来源", reading.overview?.covered_sources],
          ] as const
        ).map(([label, value]) => (
          <Content key={label} className="flex flex-col gap-0.5 md:gap-1">
            <Content as="dt">
              <Text tone="muted" size="label">
                {label}
              </Text>
            </Content>
            <Content as="dd">
              <Text
                size="metric"
                tone={value == null ? "muted" : undefined}
                title={
                  value == null ? "暂无全站统计" : "全站当前可公开阅读事件"
                }
              >
                <InlineCode>
                  {value == null ? "—" : value.toLocaleString("zh-CN")}
                </InlineCode>
              </Text>
            </Content>
          </Content>
        ))}
      </Content>
      {reading.overview ? (
        <Content aria-label="统计口径" layout="stack" className="gap-1">
          <Text size="xs" tone="muted">
            全站当前可公开阅读事件 · 统计截至 {publicationTime(observedAt)} ·
            24小时窗口（{publicationTime(reading.windowStart ?? "")}，
            {publicationTime(observedAt)}]
          </Text>
          <Text size="xs" tone="muted">
            新识别指系统建档；进展指正式事实在窗口内归入旧事件，可能重新归入。均不代表今天发生；来源数不代表平台数。
            {reading.overview.time_unknown_events > 0
              ? ` ${reading.overview.time_unknown_events} 个事件时间待核对，未归入新识别或旧事件进展统计。`
              : ""}
          </Text>
        </Content>
      ) : null}
      <Content className="@min-[56rem]/page:hidden">{notice}</Content>
      <Content className="reading-columns items-start">
        <Content as="section" aria-label="热点事件" className="min-w-0">
          <Content className="flex items-center justify-between gap-4 border-b pb-4">
            <Content className="hide-scrollbar min-w-0 overflow-x-auto">
              <ToggleGroup
                type="single"
                variant="reading"
                size="reading"
                value={category}
                aria-label="事件分类"
                onValueChange={(value) => {
                  if (value) {
                    setVisibleCount(6);
                    startTransition(() =>
                      router.push(
                        value === "all" ? "/" : `/?category=${value}`,
                      ),
                    );
                  }
                }}
              >
                {homeCategories.map(([value, label]) => (
                  <ToggleGroupItem key={value} value={value}>
                    {label}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </Content>
            <Content className="hidden @min-[64rem]/page:block">
              <SentimentLegend />
            </Content>
          </Content>
          {!storiesUnavailable ? (
            <Text size="xs" tone="muted" className="py-3">
              展示最多50条可公开事件，分类仅筛选当前集合。
              {reading.rankingBasis === "heat_then_recent"
                ? " 热度合格事件优先，其余按系统识别时间排序。"
                : ""}
            </Text>
          ) : null}
          {storiesUnavailable ? (
            <PageState
              headingLevel={2}
              state={denied ? "forbidden" : "error"}
              title={denied ? "无权读取公开事件" : "事件暂时无法读取"}
              description={
                denied
                  ? "服务拒绝了当前公开读取请求，请检查权限或重试。"
                  : "重新加载以获取最新公开事件。"
              }
              httpStatus={reading.failures?.stories?.status}
              errorCode={reading.failures?.stories?.code}
              action={
                <Button
                  variant="outline"
                  onClick={refresh}
                  disabled={isPending}
                >
                  {isPending ? "正在重新加载…" : "重新加载"}
                </Button>
              }
            />
          ) : stories.length ? (
            <HomeStoryFeed
              stories={stories.slice(0, visibleCount)}
              observedAt={observedAt}
            />
          ) : (
            <PageState
              headingLevel={2}
              state="empty"
              title={emptyCategory ? "当前分类暂无事件" : "暂无公开事件"}
              description={
                emptyCategory
                  ? "试试其他分类，或查看全部已发布的事件。"
                  : "试试探索资讯，或设置关键词监控。"
              }
              action={
                emptyCategory ? (
                  <Button
                    variant="outline"
                    disabled={isPending}
                    onClick={() => {
                      setVisibleCount(6);
                      startTransition(() => router.push("/"));
                    }}
                  >
                    查看全部事件
                  </Button>
                ) : (
                  <Content className="flex flex-wrap justify-center gap-2">
                    <Button asChild variant="outline">
                      <Link href="/discover?mode=all">探索资讯</Link>
                    </Button>
                    <Button asChild variant="outline">
                      <Link href="/monitors/new">设置关键词监测</Link>
                    </Button>
                  </Content>
                )
              }
            />
          )}
          {stories.length > visibleCount ? (
            <Content className="flex justify-center py-6">
              <Button
                variant="secondary"
                onClick={() => setVisibleCount((count) => count + 6)}
              >
                加载更多事件
              </Button>
            </Content>
          ) : null}
        </Content>
        <Content
          as="aside"
          aria-label="今日动态"
          layout="stack"
          className="gap-10"
        >
          <Content className="hidden @min-[56rem]/page:block">{notice}</Content>
          <Content
            as="section"
            aria-labelledby="home-rising"
            layout="stack"
            className="flex"
          >
            <Heading level={2} appearance="sidebar" id="home-rising">
              上升最快
            </Heading>
            <Text size="xs" tone="muted">
              当前首页集合内按增速排序 · 后端连续7个小时记录 · 与6小时前比较
            </Text>
            {storiesUnavailable ? (
              <Text size="sm" tone="muted">
                {denied
                  ? "无权读取事件热度变化。"
                  : "事件读取失败，暂时无法比较热度变化。"}
              </Text>
            ) : rising.length ? (
              rising.map((story, index) => (
                <Content key={story.id} className="flex items-start gap-4 py-2">
                  <Text size="xs" tone="muted">
                    <InlineCode>{index + 1}</InlineCode>
                  </Text>
                  <Content className="min-w-0 flex-1" layout="stack">
                    <Link href={`/discover/stories/${story.id}`}>
                      <Text size="sm">{story.title}</Text>
                    </Link>
                    <Text size="xs" tone="muted">
                      {heatTrendLabel(story.history?.trend)}
                    </Text>
                  </Content>
                  <Text size="sm">
                    <InlineCode>
                      +{story.history!.trend.percent!.toFixed(1)}%
                    </InlineCode>
                  </Text>
                </Content>
              ))
            ) : (
              <Text size="sm" tone="muted">
                暂无可比较的热度变化。
              </Text>
            )}
          </Content>
          <Content as="section" aria-labelledby="home-trends" layout="stack">
            <Heading level={2} appearance="sidebar" id="home-trends">
              事件热度趋势
            </Heading>
            <Text size="xs" tone="muted">
              当前首页集合 · 本站公开报道热度 ·
              连续7个小时记录，与6小时前比较；不代表平台榜单。
            </Text>
            {storiesUnavailable ? (
              <Text size="sm" tone="muted">
                {denied
                  ? "无权读取趋势依据。"
                  : "事件读取失败，趋势暂时不可用。"}
              </Text>
            ) : reading.stories.length ? (
              reading.stories
                .filter((story) => story.history?.trend.state === "available")
                .sort(
                  (a, b) =>
                    (b.history!.trend.percent ?? 0) -
                    (a.history!.trend.percent ?? 0),
                )
                .slice(0, 5)
                .map((story) => (
                  <Content key={story.id} layout="stack" className="gap-1">
                    <Link href={`/discover/stories/${story.id}`}>
                      <Text size="sm">{story.title}</Text>
                    </Link>
                    <Text size="xs" tone="muted">
                      {heatTrendLabel(story.history?.trend)}
                    </Text>
                  </Content>
                ))
            ) : (
              <Text size="sm" tone="muted">
                暂无公开事件可比较。
              </Text>
            )}
            {!storiesUnavailable &&
            reading.stories.length > 0 &&
            !reading.stories.some(
              (story) => story.history?.trend.state === "available",
            ) ? (
              <Text size="sm" tone="muted">
                趋势数据不足或依据不可用；请在事件中查看逐小时缺口。
              </Text>
            ) : null}
          </Content>
          <PlatformTrends
            boards={reading.platformTrends}
            failure={
              storiesUnavailable ? (reading.failures?.stories ?? {}) : undefined
            }
          />
          <Content as="section" aria-labelledby="home-daily" layout="stack">
            <Heading level={2} appearance="sidebar" id="home-daily">
              最新日报
            </Heading>
            {editionsUnavailable ? (
              <PageState
                headingLevel={2}
                state={
                  [401, 403].includes(reading.failures?.editions?.status ?? 0)
                    ? "forbidden"
                    : "error"
                }
                title="日报暂时无法读取"
                description="请重新加载，或稍后再试。"
                errorCode={reading.failures?.editions?.code}
                httpStatus={reading.failures?.editions?.status}
                action={
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={refresh}
                    disabled={isPending}
                  >
                    {isPending ? "正在重新加载…" : "重试日报"}
                  </Button>
                }
              />
            ) : reading.editions.length ? (
              reading.editions.slice(0, 1).map((edition) => (
                <Content key={edition.key} layout="stack" className="gap-2">
                  <Heading level={3} appearance="result">
                    <Link href={edition.reading_url}>{edition.title}</Link>
                  </Heading>
                  <Text tone="muted" size="xs">
                    刊期 <InlineCode>{edition.key}</InlineCode> ·{" "}
                    <InlineCode>
                      {publicationTime(edition.created_at)}
                    </InlineCode>{" "}
                    生成
                  </Text>
                </Content>
              ))
            ) : (
              <Text size="sm" tone="muted">
                暂无已发布日报，发布后可在这里阅读。
              </Text>
            )}
            <Button asChild variant="ghost" size="sm" className="self-start">
              <Link href="/reports/daily">
                阅读日报
                <ArrowUpRightIcon data-icon="inline-end" />
              </Link>
            </Button>
          </Content>
        </Content>
      </Content>
    </Content>
  );
}

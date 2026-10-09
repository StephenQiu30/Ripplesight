"use client";

import { AuthLink as Link } from "@/components/auth/auth-link";
import { useEffect, useId, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { SearchIcon, ArrowUpRightIcon } from "lucide-react";
import { HomeStoryFeed } from "./home-feed";
import { homeUpdatedAt, homeCategories, type HomeReading } from "./home-format";
import { Button } from "@/components/ui/button";
import {
  Content,
  Heading,
  Text,
  InlineCode,
  Form,
} from "@/components/ui/content";
import { Field, FieldLabel } from "@/components/ui/field";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { SignalNotice, SentimentLegend } from "@/components/ui/signal";
import { PageState } from "@/components/system/page-state";
import { LoadingSignal } from "@/components/system/global-loading";
import { useLayoutScrollContainer } from "@/layout/basic-layout";
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
  const observedAt = reading.observedAt ?? "1970-01-01T00:00:00Z";
  const updatedAt = homeUpdatedAt(reading);
  const rising = reading.stories
    .filter((s) => s.attention?.trend === "up" && s.attention.trend_pct != null)
    .sort((a, b) => b.attention!.trend_pct! - a.attention!.trend_pct!)
    .slice(0, 5);
  const denied = [401, 403].includes(reading.failures?.stories?.status ?? 0);
  const storiesUnavailable = reading.unavailable.includes("stories");
  const editionsUnavailable = reading.unavailable.includes("editions");
  const emptyCategory = category !== "all" && reading.stories.length > 0;
  const notice = (
    <SignalNotice title="负面突增提醒">
      <Text size="sm" tone="muted">
        暂无公开舆情数据，收到有效观测后将在这里展示提醒。
      </Text>
    </SignalNotice>
  );
  return (
    <Content layout="stack" className="gap-8" aria-busy={isPending}>
      <LoadingSignal active={isPending} />
      <Content
        as="header"
        className="flex flex-wrap items-end justify-between gap-4"
      >
        <Content layout="stack" className="gap-1">
          <Heading level={1}>今日 AI 热点</Heading>
          <Text size="xs" tone="muted">
            {updatedAt
              ? `更新于 ${publicationTime(updatedAt)}`
              : "公开事件发布后显示更新时间"}
          </Text>
        </Content>
        <Content className="hidden items-center gap-2 md:flex">
          <Form
            action="/discover"
            role="search"
            aria-label="搜索事件、主题或来源"
            className="w-70"
          >
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
          </Form>
          <Button asChild>
            <Link href="/feed/daily.xml">订阅日报</Link>
          </Button>
        </Content>
      </Content>
      <Content
        as="section"
        aria-label="个人关键词监控"
        className="flex flex-wrap items-center justify-between gap-4 rounded-xl border p-4"
      >
        <Content layout="stack" className="gap-1">
          <Heading level={2} appearance="sidebar">
            关注你自己的关键词
          </Heading>
          <Text tone="muted" size="sm">
            填写关键词，选择已接入的平台，在监控主题中查看相关帖子与评论。个人结果由你决定何时采集。
          </Text>
        </Content>
        <Content className="flex flex-wrap gap-2">
          <Button asChild>
            <Link href="/monitors/new">设置关键词</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/sources">平台接入</Link>
          </Button>
        </Content>
      </Content>
      <Content
        as="dl"
        aria-label="今日概览"
        className="grid grid-cols-2 gap-x-8 gap-y-6 border-y py-5 md:grid-cols-4"
      >
        {["追踪中事件", "过去 24 小时新增", "覆盖平台", "负面突增"].map(
          (label) => (
            <Content key={label} className="flex flex-col gap-1">
              <Content as="dt">
                <Text tone="muted" size="xs">
                  {label}
                </Text>
              </Content>
              <Content as="dd">
                <Text size="metric" tone="muted" title="暂无全站统计">
                  <InlineCode>—</InlineCode>
                </Text>
              </Content>
            </Content>
          ),
        )}
      </Content>
      <Content className="lg:hidden">{notice}</Content>
      <Content className="reading-columns items-start">
        <Content as="section" aria-label="热点事件" className="min-w-0">
          <Content className="flex items-center justify-between gap-4 border-b pb-4">
            <Content className="hide-scrollbar min-w-0 overflow-x-auto">
              <ToggleGroup
                type="single"
                variant="reading"
                size="default"
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
            <Content className="hidden xl:block">
              <SentimentLegend />
            </Content>
          </Content>
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
                  : "公开事件发布后，这里会显示进展、来源与热度。你也可以先探索资讯，或设置自己的关键词监控。"
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
                ) : undefined
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
          <Content className="hidden lg:block">{notice}</Content>
          <Content as="section" aria-labelledby="home-rising" layout="stack">
            <Heading level={2} appearance="sidebar" id="home-rising">
              上升最快
            </Heading>
            <Text size="xs" tone="muted">
              当前可比较的公开事件 · 48 小时窗口
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
                  <Link
                    href={`/discover/stories/${story.id}`}
                    className="min-w-0 flex-1"
                  >
                    <Text size="sm">{story.title}</Text>
                  </Link>
                  <Text size="sm">
                    <InlineCode>
                      +{story.attention!.trend_pct!.toFixed(0)}%
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
              X 今日趋势
            </Heading>
            <Content className="border-y py-8">
              <Text size="sm" tone="muted">
                暂无公开趋势快照。
              </Text>
            </Content>
          </Content>
          <Content as="section" aria-labelledby="home-daily" layout="stack">
            <Heading level={2} appearance="sidebar" id="home-daily">
              今日日报
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
                    <InlineCode>
                      {publicationTime(edition.created_at)}
                    </InlineCode>{" "}
                    生成
                  </Text>
                </Content>
              ))
            ) : (
              <Text size="sm" tone="muted">
                今日日报尚未发布，发布后可在这里阅读。
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

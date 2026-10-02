import Link from "next/link";
import Image from "next/image";

import { LocalReadingPreferences } from "@/components/publication/local-reading";

import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/request";

export const categories = [
  ["ai-models", "模型"],
  ["ai-products", "产品"],
  ["industry", "行业"],
  ["paper", "论文"],
  ["tip", "技巧"],
  ["opinion", "观点"],
] as const;

export function publicationTime(value: string | null) {
  if (!value || Number.isNaN(new Date(value).getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function PublicationNavigation() {
  return (
    <>
      <nav
        aria-label="资讯阅读入口"
        className="mb-8 flex flex-wrap gap-5 text-sm"
      >
        <Link href="/discover">资讯</Link>
        <Link href="/discover/topics">行业专题</Link>
        <Link href="/reports/daily">日周月刊</Link>
        <Link href="/feeds">订阅</Link>
        <Link href="/agent">Agent 接入</Link>
        <Link href="/publication/manage">发布管理</Link>
        <LocalReadingPreferences />
      </nav>
    </>
  );
}

export function PublicationFailure({
  error,
  href,
}: {
  error: unknown;
  href: string;
}) {
  const known = error instanceof ApiRequestError ? error : null;
  return (
    <PageState
      eyebrow="读取未完成"
      title={
        known?.code === "publication_search_busy"
          ? "检索暂时繁忙"
          : known?.status === 404
            ? "这份材料目前不可公开阅读"
            : "暂时无法读取资讯"
      }
      description={
        known?.code === "publication_search_busy"
          ? "请缩小时间或来源范围，或稍后重新检索。本次没有返回截断结果。"
          : known?.status === 404
            ? "材料不存在、已撤回或许可已经变化。"
            : "请重新加载；读取不会触发来源请求或模型调用。"
      }
      action={
        <Button asChild variant="outline">
          <Link href={href}>重新读取</Link>
        </Button>
      }
    />
  );
}

export function PublicItemCards({
  items,
}: {
  items: HotKeyAPI.PublicItemView[];
}) {
  if (!items.length)
    return (
      <p className="text-muted-foreground py-12 text-sm">
        当前条件下还没有可公开的资讯。
      </p>
    );
  return (
    <div className="divide-muted divide-y">
      {items.map((item) => (
        <article key={item.id} className="space-y-3 py-7">
          <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
            <span>
              {item.source.icon_url &&
              [
                `/api/site/source-icons/${encodeURIComponent(item.source.key)}.svg`,
                `/api/site/source-icons/${encodeURIComponent(item.source.key)}/avatar-48`,
              ].includes(item.source.icon_url) ? (
                <Image
                  src={item.source.icon_url}
                  alt=""
                  unoptimized
                  width={16}
                  height={16}
                  className="mr-2 inline-block h-4 w-4 rounded-sm"
                />
              ) : null}
              {item.source.name}
              {item.source.first_party ? " · 第一方" : ""}
            </span>
            <time dateTime={item.timeline_at}>
              {publicationTime(item.timeline_at)}
            </time>
            {item.category ? (
              <span>
                {categories.find(([key]) => key === item.category)?.[1]}
              </span>
            ) : null}
            {item.selected ? <span>精选</span> : null}
          </div>
          <h2 className="text-lg leading-7 font-medium">
            <Link href={item.reading_url}>{item.title}</Link>
          </h2>
          {item.summary ? (
            <p className="text-muted-foreground text-sm leading-7">
              {item.summary}
            </p>
          ) : null}
          <div className="text-muted-foreground flex flex-wrap gap-3 text-xs">
            {item.tags.map((tag) => (
              <span key={tag}>#{tag}</span>
            ))}
            {item.original_url ? (
              <a href={item.original_url} target="_blank" rel="noreferrer">
                来源原文 ↗
              </a>
            ) : null}
            {item.event_id ? (
              <Link href={`/discover/stories/${item.event_id}`}>查看事件</Link>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}

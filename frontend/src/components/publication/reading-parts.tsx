import { Badge } from "@/components/ui/badge";
import {
  Item,
  ItemContent,
  ItemGroup,
  ItemTitle,
  ItemDescription,
} from "@/components/ui/item";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import Link from "next/link";
import Image from "next/image";

export { PublicationNavigation } from "./reading-navigation";

import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
        known?.code === "publication_not_configured"
          ? "公开资讯尚未发布"
          : known?.code === "publication_search_busy"
            ? "检索暂时繁忙"
            : known?.status === 404
              ? "这份材料目前不可公开阅读"
              : "暂时无法读取资讯"
      }
      description={
        known?.code === "publication_not_configured"
          ? "公开资料发布后即可阅读，登录后仍可使用个人关注与报告。"
          : known?.code === "publication_search_busy"
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
      <Empty className="py-12">
        <EmptyHeader>
          <EmptyDescription>当前条件下还没有可公开的资讯。</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  return (
    <ItemGroup>
      {items.map((item) => (
        <Item asChild key={item.id}>
          <article role="listitem">
            <ItemContent className="min-w-0 gap-3">
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
                      className="mr-2 inline-block size-4 rounded-sm"
                    />
                  ) : null}
                  {item.source.name}
                  {item.source.first_party ? " · 第一方" : ""}
                </span>
                <time dateTime={item.timeline_at}>
                  {item.published_at ? "发布于 " : "发现于 "}
                  {publicationTime(item.timeline_at)}
                </time>
                {item.backfill ? <span>历史导入</span> : null}
                {item.analysis_state === "not_analyzed" ? (
                  <span>未分析</span>
                ) : null}
                {item.category ? (
                  <span>
                    {categories.find(([key]) => key === item.category)?.[1]}
                  </span>
                ) : null}
                {item.selected ? <Badge variant="secondary">精选</Badge> : null}
              </div>
              <ItemTitle className="line-clamp-none">
                <h2>
                  <Link href={item.reading_url}>{item.title}</Link>
                </h2>
              </ItemTitle>
              {item.summary ? (
                <ItemDescription className="line-clamp-none">
                  {item.summary_origin === "source" ? (
                    <span>来源摘要： </span>
                  ) : null}
                  {item.summary}
                </ItemDescription>
              ) : item.analysis_state === "not_analyzed" ? (
                <ItemDescription>
                  来源未提供摘要，可前往原文阅读。
                </ItemDescription>
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
                  <Link href={`/discover/stories/${item.event_id}`}>
                    查看事件
                  </Link>
                ) : null}
              </div>
            </ItemContent>
          </article>
        </Item>
      ))}
    </ItemGroup>
  );
}

export function PublicSourceStatus({
  sources,
}: {
  sources: HotKeyAPI.PublicSourceStatusView[];
}) {
  const affected = sources.filter(
    (source) =>
      !source.enabled || ["degraded", "failing"].includes(source.health),
  );
  if (!affected.length) return null;
  return (
    <Alert className="mb-5">
      <AlertTitle>部分来源暂未更新</AlertTitle>
      <AlertDescription>
        <ul className="space-y-2">
          {affected.map((source) => (
            <li key={source.source_key}>
              {source.name} ·{" "}
              {!source.enabled
                ? "已暂停"
                : source.health === "failing"
                  ? "采集失败"
                  : "采集不完整"}
              {" · "}最近成功：{publicationTime(source.last_success_at)}
            </li>
          ))}
        </ul>
        <p>已保存且许可仍有效的资讯可以继续阅读。</p>
      </AlertDescription>
    </Alert>
  );
}

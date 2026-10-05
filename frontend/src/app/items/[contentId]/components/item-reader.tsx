"use client";
import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuLink,
} from "@/components/ui/navigation-menu";
import {
  Item,
  ItemContent,
  ItemTitle,
  ItemDescription,
} from "@/components/ui/item";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Viewer } from "@/components/editor";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { SaveItem, MarkItemRead } from "@/components/publication/local-reading";
import { MediaGallery } from "@/components/publication/media-gallery";
import { GroupExpansion } from "@/components/publication/reading-groups";
import { PosterDownload } from "@/components/publication/poster-download";
import { publicationTime } from "@/components/publication/reading-parts";
import { Button } from "@/components/ui/button";
import { useLayoutScrollContainer } from "@/layout/basic-layout";

const translationLabels = {
  not_requested: "尚未生成译文",
  queued: "译文等待处理",
  running: "译文处理中",
  complete: "完整译文",
  partial: "部分译文",
  unknown: "译文回执未知，等待人工复核",
  failed: "译文处理失败",
  stale: "译文材料或许可已变化",
} as const;

export function ItemReader({ item }: { item: HotKeyAPI.PublicItemDetailView }) {
  const scrollContainer = useLayoutScrollContainer();
  const key = `hotkey.reading.v1.${item.id}.${item.revision}`;
  const [readingState, setReadingState] = useState({
    key,
    mode: "original" as "original" | "translated",
    loaded: false,
  });
  const mode = readingState.key === key ? readingState.mode : "original";
  const readingRef = useRef(readingState);
  useEffect(() => {
    readingRef.current = readingState;
  }, [readingState]);
  useEffect(() => {
    const scrollElement = scrollContainer?.current;
    let restoreFrame: number | null = null;
    const frame = requestAnimationFrame(() => {
      try {
        const saved = JSON.parse(localStorage.getItem(key) ?? "{}");
        setReadingState({
          key,
          mode:
            saved.mode === "translated" && item.body?.translated
              ? "translated"
              : "original",
          loaded: true,
        });
        if (
          typeof saved.scroll === "number" &&
          Number.isFinite(saved.scroll) &&
          saved.scroll >= 0
        )
          restoreFrame = requestAnimationFrame(() => {
            if (scrollElement) scrollElement.scrollTop = saved.scroll;
          });
      } catch {
        setReadingState({ key, mode: "original", loaded: true });
      }
    });
    return () => {
      cancelAnimationFrame(frame);
      if (restoreFrame !== null) cancelAnimationFrame(restoreFrame);
    };
  }, [key, item.body?.translated, scrollContainer]);
  useEffect(() => {
    const scrollElement = scrollContainer?.current;
    const save = () => {
      const current = readingRef.current;
      if (current.key !== key || !current.loaded) return;
      try {
        localStorage.setItem(
          key,
          JSON.stringify({
            mode: current.mode,
            scroll: scrollElement?.scrollTop ?? 0,
          }),
        );
      } catch {
        /* Optional local state. */
      }
    };
    window.addEventListener("pagehide", save);
    return () => {
      save();
      window.removeEventListener("pagehide", save);
    };
  }, [key, scrollContainer]);
  const html =
    mode === "translated" ? item.body?.translated : item.body?.original_html;
  return (
    <div>
      <MarkItemRead id={item.id} />
      <div className="text-muted-foreground mb-5 flex flex-wrap gap-4 text-xs">
        <span>{item.source.name}</span>
        <span>
          {item.published_at ? "发布于 " : "发现于 "}
          {publicationTime(item.published_at ?? item.timeline_at)}
        </span>
        {item.backfill ? <span>历史导入</span> : null}
        {item.analysis_state === "not_analyzed" ? <span>未分析</span> : null}
        <span>公开修订 {item.revision}</span>
      </div>
      <h1 className="max-w-4xl text-3xl leading-tight font-medium tracking-tight sm:text-4xl">
        {item.title}
      </h1>
      {item.original_title && item.original_title !== item.title ? (
        <p className="text-muted-foreground mt-4 text-sm">
          {item.original_title}
        </p>
      ) : null}
      {item.body && item.summary ? (
        <p className="text-muted-foreground my-7 max-w-3xl text-base leading-8">
          {item.summary_origin === "source" ? <span>来源摘要： </span> : null}
          {item.summary}
        </p>
      ) : null}
      <div className="my-7 flex flex-wrap items-start gap-3">
        <SaveItem id={item.id} />
        {item.original_url ? (
          <Button asChild variant="outline">
            <a href={item.original_url} target="_blank" rel="noreferrer">
              来源原文 ↗
            </a>
          </Button>
        ) : null}
        {item.markdown_available ? (
          <>
            <Button asChild variant="outline">
              <a href={`/items/${item.id}.md`} download>
                下载 Markdown
              </a>
            </Button>
            <PosterDownload target={{ contentId: item.id }} />
          </>
        ) : null}
        <Button
          variant="outline"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(window.location.href);
              toast.success("阅读链接已复制。");
            } catch {
              toast.error("暂时无法复制，请复制浏览器地址。");
            }
          }}
        >
          复制阅读链接
        </Button>
        <Button asChild variant="ghost">
          <Link
            href={`/publication/manage?content_id=${encodeURIComponent(item.id)}`}
          >
            管理这篇资讯
          </Link>
        </Button>
        {item.event_id ? (
          <Button asChild variant="outline">
            <Link href={`/discover/stories/${item.event_id}`}>查看事件</Link>
          </Button>
        ) : null}
      </div>
      <p className="text-muted-foreground mb-7 text-xs">
        {item.license_name}
        {item.license_url ? (
          <>
            {" "}
            ·{" "}
            <a
              href={item.license_url}
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              许可说明
            </a>
          </>
        ) : null}
      </p>
      {item.body ? (
        <>
          <div className="mb-6 flex flex-wrap items-center gap-3">
            <Button
              variant={mode === "original" ? "secondary" : "ghost"}
              onClick={() =>
                setReadingState((state) => ({ ...state, mode: "original" }))
              }
            >
              原文
            </Button>
            <Button
              disabled={!item.body.translated}
              variant={mode === "translated" ? "secondary" : "ghost"}
              onClick={() =>
                setReadingState((state) => ({ ...state, mode: "translated" }))
              }
            >
              中文译文
            </Button>
            <span className="text-muted-foreground text-xs">
              {
                translationLabels[
                  item.body.translation_state ?? "not_requested"
                ]
              }
            </span>
          </div>
          <div className="grid gap-10 lg:grid-cols-4">
            <article className="[&_pre]:bg-muted max-w-none text-sm leading-8 break-words lg:col-span-3 [&_a]:underline [&_a]:underline-offset-4 [&_blockquote]:my-4 [&_blockquote]:pl-5 [&_h2]:mt-10 [&_h2]:mb-4 [&_h2]:text-xl [&_h2]:font-medium [&_h3]:mt-7 [&_h3]:font-medium [&_img]:h-auto [&_img]:max-w-full [&_li]:ml-5 [&_p]:my-4 [&_pre]:my-5 [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:p-4 [&_table]:my-5 [&_table]:block [&_table]:overflow-x-auto [&_td]:p-2 [&_th]:p-2 [&_video]:max-w-full">
              {mode === "translated" && !item.body.translation_complete ? (
                <Alert role="status" className="p-4">
                  <AlertDescription>
                    这份译文尚未完整，原文仍可切换阅读。
                  </AlertDescription>
                </Alert>
              ) : null}
              {html ? (
                <Viewer value={html} format="html" />
              ) : (
                <Viewer value={item.body.original} format="text" />
              )}
            </article>
            <aside className="flex flex-col gap-y-8">
              {item.body.outline?.length && mode === "original" ? (
                <NavigationMenu
                  viewport={false}
                  orientation="vertical"
                  aria-label="文章目录"
                  className="max-w-full items-start"
                >
                  <NavigationMenuList className="flex-col items-start gap-2">
                    {item.body.outline.map((entry) => (
                      <NavigationMenuItem key={entry.id}>
                        <NavigationMenuLink asChild>
                          <a href={`#${entry.id}`}>{entry.title}</a>
                        </NavigationMenuLink>
                      </NavigationMenuItem>
                    ))}
                  </NavigationMenuList>
                </NavigationMenu>
              ) : null}
              {item.body.media?.length ? (
                <MediaGallery media={item.body.media} />
              ) : null}
            </aside>
          </div>
        </>
      ) : item.summary ? (
        <article
          aria-label="来源内容"
          className="max-w-3xl text-base leading-8 break-words [&_p]:my-4"
        >
          <p className="text-muted-foreground text-xs">
            {item.summary_origin === "source" ? "来源摘要" : "资讯摘要"}
          </p>
          <Viewer value={item.summary} format="text" />
        </article>
      ) : (
        <Alert role="note" className="p-5 leading-7">
          <AlertDescription>
            此条记录仅包含标题和来源信息，尚未获取可在站内展示的内容。
          </AlertDescription>
        </Alert>
      )}
      {item.quoted_post ? (
        <Item variant="outline" asChild>
          <section aria-label="引用帖子" className="mt-10 max-w-3xl p-5">
            <ItemContent className="min-w-0 gap-3">
              <ItemTitle className="line-clamp-none w-full">
                <h2>引用帖子</h2>
              </ItemTitle>
              <ItemDescription className="mt-2 line-clamp-none">
                {item.quoted_post.author ? `${item.quoted_post.author} · ` : ""}
                {item.quoted_post.item.source.name}
              </ItemDescription>
              <Link
                href={item.quoted_post.item.reading_url}
                className="mt-3 block font-medium underline underline-offset-4"
              >
                {item.quoted_post.item.title}
              </Link>
              {item.quoted_post.item.summary ? (
                <ItemDescription className="mt-3 line-clamp-none leading-7">
                  {item.quoted_post.item.summary}
                </ItemDescription>
              ) : null}
              {item.quoted_post.body ? (
                <div className="mt-4 text-sm leading-8 break-words [&_a]:underline [&_img]:h-auto [&_img]:max-w-full [&_p]:my-3 [&_pre]:overflow-x-auto">
                  {item.quoted_post.body.original_html ? (
                    <Viewer
                      value={item.quoted_post.body.original_html}
                      format="html"
                    />
                  ) : (
                    <Viewer
                      value={item.quoted_post.body.original}
                      format="text"
                    />
                  )}
                  {item.quoted_post.body.media?.length ? (
                    <MediaGallery media={item.quoted_post.body.media} />
                  ) : null}
                </div>
              ) : null}
            </ItemContent>
          </section>
        </Item>
      ) : null}
      {item.fact_id ? (
        <section
          className="mt-10 flex max-w-3xl flex-col gap-y-4"
          aria-label="其他报道与进展"
        >
          <h2 className="text-lg font-medium">其他报道与进展</h2>
          <GroupExpansion
            group={{ fact_id: item.fact_id, event_id: item.event_id }}
            filters={{ channel: "all" }}
          />
        </section>
      ) : null}
      {item.related_stories?.length ? (
        <section
          className="mt-10 flex max-w-3xl flex-col gap-y-4"
          aria-label="相关事件"
        >
          <h2 className="text-lg font-medium">相关事件</h2>
          {item.related_stories.map((story) => (
            <Item variant="outline" key={story.id} asChild>
              <article className="p-4">
                <ItemContent className="min-w-0 gap-3">
                  <Link
                    href={story.reading_url}
                    className="font-medium underline underline-offset-4"
                  >
                    {story.title}
                  </Link>
                  {story.summary ? (
                    <ItemDescription className="mt-2 line-clamp-none leading-7">
                      {story.summary}
                    </ItemDescription>
                  ) : null}
                  <ItemDescription className="mt-2 line-clamp-none">
                    {story.supporting_reports} 篇独立报道支持关联
                  </ItemDescription>
                </ItemContent>
              </article>
            </Item>
          ))}
        </section>
      ) : null}
    </div>
  );
}

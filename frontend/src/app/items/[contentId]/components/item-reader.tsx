"use client";
import { Textarea } from "@/components/ui/textarea";
import { FieldLabel } from "@/components/ui/field";

import Link from "next/link";
import { useEffect, useState } from "react";
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
  const [mode, setMode] = useState<"original" | "translated">("original");
  const [note, setNote] = useState("");
  const key = `hotkey.reading.v1.${item.id}.${item.revision}`;
  useEffect(() => {
    const scrollElement = scrollContainer?.current;
    let restoreFrame: number | null = null;
    const frame = requestAnimationFrame(() => {
      try {
        const saved = JSON.parse(localStorage.getItem(key) ?? "{}");
        if (typeof saved.note === "string") setNote(saved.note.slice(0, 2000));
        if (saved.mode === "translated" && item.body?.translated)
          setMode("translated");
        if (typeof saved.scroll === "number" && saved.scroll >= 0)
          restoreFrame = requestAnimationFrame(() => {
            if (scrollElement) scrollElement.scrollTop = saved.scroll;
          });
      } catch {
        /* Reading works when local storage is unavailable. */
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
      try {
        localStorage.setItem(
          key,
          JSON.stringify({ note, mode, scroll: scrollElement?.scrollTop ?? 0 }),
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
  }, [key, note, mode, scrollContainer]);
  const html =
    mode === "translated" ? item.body?.translated : item.body?.original_html;
  return (
    <div>
      <MarkItemRead id={item.id} />
      <div className="text-muted-foreground mb-5 flex flex-wrap gap-4 text-xs">
        <span>{item.source.name}</span>
        <span>{publicationTime(item.published_at ?? item.timeline_at)}</span>
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
      {item.summary ? (
        <p className="text-muted-foreground my-7 max-w-3xl text-base leading-8">
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
              onClick={() => setMode("original")}
            >
              原文
            </Button>
            <Button
              disabled={!item.body.translated}
              variant={mode === "translated" ? "secondary" : "ghost"}
              onClick={() => setMode("translated")}
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
                <p role="status" className="bg-muted rounded-md p-4">
                  这份译文尚未完整，原文仍可切换阅读。
                </p>
              ) : null}
              {html ? (
                <div dangerouslySetInnerHTML={{ __html: html }} />
              ) : (
                <p className="whitespace-pre-wrap">{item.body.original}</p>
              )}
            </article>
            <aside className="flex flex-col gap-y-8">
              {item.body.outline?.length && mode === "original" ? (
                <nav aria-label="文章目录">
                  <h2 className="text-sm font-medium">目录</h2>
                  <ul className="mt-3 flex flex-col gap-y-3 text-xs leading-5">
                    {item.body.outline.map((entry) => (
                      <li key={entry.id}>
                        <a href={`#${entry.id}`}>{entry.title}</a>
                      </li>
                    ))}
                  </ul>
                </nav>
              ) : null}
              {item.body.media?.length ? (
                <MediaGallery media={item.body.media} />
              ) : null}
            </aside>
          </div>
        </>
      ) : (
        <p className="bg-muted rounded-md p-5 text-sm leading-7">
          当前以摘要阅读。全文可前往来源原文查看。
        </p>
      )}
      {item.quoted_post ? (
        <section
          aria-label="引用帖子"
          className="mt-10 max-w-3xl rounded-lg border p-5"
        >
          <h2 className="text-sm font-medium">引用帖子</h2>
          <p className="text-muted-foreground mt-2 text-xs">
            {item.quoted_post.author ? `${item.quoted_post.author} · ` : ""}
            {item.quoted_post.item.source.name}
          </p>
          <Link
            href={item.quoted_post.item.reading_url}
            className="mt-3 block font-medium underline underline-offset-4"
          >
            {item.quoted_post.item.title}
          </Link>
          {item.quoted_post.item.summary ? (
            <p className="text-muted-foreground mt-3 text-sm leading-7">
              {item.quoted_post.item.summary}
            </p>
          ) : null}
          {item.quoted_post.body ? (
            <div className="mt-4 text-sm leading-8 break-words [&_a]:underline [&_img]:h-auto [&_img]:max-w-full [&_p]:my-3 [&_pre]:overflow-x-auto">
              {item.quoted_post.body.original_html ? (
                <div
                  dangerouslySetInnerHTML={{
                    __html: item.quoted_post.body.original_html,
                  }}
                />
              ) : (
                <p className="whitespace-pre-wrap">
                  {item.quoted_post.body.original}
                </p>
              )}
              {item.quoted_post.body.media?.length ? (
                <MediaGallery media={item.quoted_post.body.media} />
              ) : null}
            </div>
          ) : null}
        </section>
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
            <article key={story.id} className="rounded-lg border p-4">
              <Link
                href={story.reading_url}
                className="font-medium underline underline-offset-4"
              >
                {story.title}
              </Link>
              {story.summary ? (
                <p className="text-muted-foreground mt-2 text-sm leading-7">
                  {story.summary}
                </p>
              ) : null}
              <p className="text-muted-foreground mt-2 text-xs">
                {story.supporting_reports} 篇独立报道支持关联
              </p>
            </article>
          ))}
        </section>
      ) : null}
      <section className="mt-12 max-w-3xl">
        <FieldLabel htmlFor="reading-note">本机阅读笔记</FieldLabel>
        <Textarea
          id="reading-note"
          maxLength={2000}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          className="mt-3 block min-h-24 w-full p-4"
        />
        <Button
          variant="outline"
          className="mt-3"
          onClick={() => {
            try {
              localStorage.setItem(
                key,
                JSON.stringify({
                  note,
                  mode,
                  scroll: scrollContainer?.current?.scrollTop ?? 0,
                }),
              );
              toast.success("已保存在本机。");
            } catch {
              toast.error("本机存储不可用，未保存。");
            }
          }}
        >
          保存笔记
        </Button>
      </section>
    </div>
  );
}

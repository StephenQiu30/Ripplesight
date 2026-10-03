"use client";
import { ChevronDownIcon } from "lucide-react";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { listCodexResetPosts } from "@/api/zhongzhigonggao";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { ApiRequestError } from "@/request";
import { beijingTime } from "./reset-timeline";

type Filter = NonNullable<HotKeyAPI.listCodexResetPostsParams["filter_key"]>;
type PostsState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; posts: HotKeyAPI.ResetPostView[] };
const filters: { value: Filter; label: string }[] = [
  { value: "all", label: "全部帖子" },
  { value: "relevant", label: "有关公告" },
  { value: "pending", label: "待处理" },
  { value: "review", label: "需复核" },
];

export function ResetSourcePosts({ refresh }: { refresh: number }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const [state, setState] = useState<PostsState>({ status: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    void listCodexResetPosts(
      { page, filter_key: filter },
      { signal: controller.signal },
    )
      .then((posts) => {
        if (!controller.signal.aborted) setState({ status: "ready", posts });
      })
      .catch((error) => {
        if (
          !controller.signal.aborted &&
          !(error instanceof ApiRequestError && error.kind === "cancelled")
        ) {
          setState({ status: "error" });
          toast.error(
            error instanceof ApiRequestError
              ? `${error.message}${error.requestId ? ` 请求编号：${error.requestId}` : ""}`
              : "源帖子读取失败。",
          );
        }
      });
    return () => controller.abort();
  }, [page, filter, retry, refresh]);
  function chooseFilter(value: Filter) {
    if (value === filter && page === 1) return;
    setState({ status: "loading" });
    setPage(1);
    setFilter(value);
  }
  function move(delta: number) {
    setState({ status: "loading" });
    setPage((value) => value + delta);
  }
  return (
    <section aria-label="公告源帖子" className="mt-14 flex flex-col gap-y-6">
      <div>
        <h2 className="text-xl font-medium">公告源帖子</h2>
        <p className="text-muted-foreground mt-2 text-sm">
          固定源原文、上下文和处理状态。未处理或失败的帖子保留未知状态。
        </p>
      </div>
      <div
        className="flex flex-wrap gap-2"
        role="group"
        aria-label="帖子状态筛选"
      >
        {filters.map((item) => (
          <Button
            key={item.value}
            variant={filter === item.value ? "secondary" : "ghost"}
            aria-pressed={filter === item.value}
            onClick={() => chooseFilter(item.value)}
          >
            {item.label}
          </Button>
        ))}
      </div>
      {state.status === "loading" && (
        <p role="status" className="text-muted-foreground">
          正在读取帖子…
        </p>
      )}
      {state.status === "error" && (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>源帖子暂不可读</EmptyTitle>
          </EmptyHeader>
          <Button
            variant="outline"
            onClick={() => {
              setState({ status: "loading" });
              setRetry((value) => value + 1);
            }}
          >
            重试读取帖子
          </Button>
        </Empty>
      )}
      {state.status === "ready" && (
        <>
          {state.posts.length === 0 && (
            <p className="text-muted-foreground py-6">当前筛选没有帖子。</p>
          )}
          <ol className="flex flex-col gap-y-8">
            {state.posts.map((post) => (
              <li key={post.id} className="flex flex-col gap-y-3">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="text-muted-foreground">
                    {beijingTime(post.published_at)}
                  </span>
                  <Badge variant="secondary">
                    {post.needs_review && !post.reviewed
                      ? "待复核"
                      : post.processed_at
                        ? "已处理"
                        : "待处理"}
                  </Badge>
                  {post.failure_count > 0 && (
                    <Badge variant="outline">
                      识别失败 {post.failure_count} 次
                    </Badge>
                  )}
                </div>
                {post.translation_zh && (
                  <p className="leading-7 whitespace-pre-wrap">
                    {post.translation_zh}
                  </p>
                )}
                <Collapsible
                  className="text-sm"
                  defaultOpen={!post.translation_zh}
                >
                  <CollapsibleTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
                    >
                      <span className="min-w-0 text-left">原文与上下文</span>
                      <ChevronDownIcon
                        aria-hidden="true"
                        data-icon="inline-end"
                        className="group-data-[state=open]:rotate-180"
                      />
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent
                    forceMount
                    className="data-[state=closed]:hidden"
                  >
                    <p className="mt-3 leading-7 whitespace-pre-wrap">
                      {post.text}
                    </p>
                    {post.context.map((context) => (
                      <blockquote
                        key={`${context.relation}-${context.id}`}
                        className="bg-muted/40 mt-3 rounded-lg p-4"
                      >
                        <p className="text-muted-foreground mb-2">
                          {context.relation === "reply"
                            ? "回复上下文"
                            : "引用上下文"}{" "}
                          · {context.author}
                        </p>
                        <p className="leading-6 whitespace-pre-wrap">
                          {context.text_zh ?? context.original_text}
                        </p>
                        <Button asChild variant="link" className="px-0">
                          <a
                            href={context.url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            阅读上下文原帖
                          </a>
                        </Button>
                      </blockquote>
                    ))}
                  </CollapsibleContent>
                </Collapsible>
                <Button asChild variant="link" className="px-0">
                  <a href={post.url} target="_blank" rel="noopener noreferrer">
                    阅读源帖子
                  </a>
                </Button>
              </li>
            ))}
          </ol>
        </>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="outline"
          disabled={page === 1 || state.status !== "ready"}
          onClick={() => move(-1)}
        >
          上一页帖子
        </Button>
        <span className="text-muted-foreground text-sm">
          第 {page} 页，每页最多 50 条
        </span>
        <Button
          variant="outline"
          disabled={
            state.status !== "ready" || state.posts.length < 50 || page >= 1000
          }
          onClick={() => move(1)}
        >
          下一页帖子
        </Button>
      </div>
    </section>
  );
}

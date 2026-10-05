"use client";
import * as UI from "@/components/ui/content";

import { Spinner } from "@/components/ui/spinner";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
} from "@/components/ui/item";
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
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/empty";
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
    <UI.Content
      as="section"
      aria-label="公告源帖子"
      className="mt-14 flex flex-col gap-y-6"
    >
      <UI.Content>
        <UI.Heading level={2} className="text-xl font-medium">
          公告源帖子
        </UI.Heading>
        <UI.Text className="text-muted-foreground mt-2 text-sm">
          固定源原文、上下文和处理状态。未处理或失败的帖子保留未知状态。
        </UI.Text>
      </UI.Content>
      <ToggleGroup
        type="single"
        value={filter}
        onValueChange={(value) => value && chooseFilter(value as typeof filter)}
        className="flex flex-wrap gap-2"
        aria-label="帖子状态筛选"
      >
        {filters.map((item) => (
          <ToggleGroupItem key={item.value} value={item.value}>
            {item.label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      {state.status === "loading" && (
        <Item role="status">
          <Spinner aria-hidden="true" />
          <ItemContent>
            <ItemDescription className="line-clamp-none">
              正在读取帖子…
            </ItemDescription>
          </ItemContent>
        </Item>
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
            <Empty className="py-6">
              <EmptyHeader>
                <EmptyDescription>当前筛选没有帖子。</EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
          <ItemGroup className="flex flex-col gap-y-8">
            {state.posts.map((post) => (
              <Item
                role="listitem"
                variant="default"
                key={post.id}
                className="flex flex-col gap-y-3"
              >
                <ItemContent className="min-w-0 gap-3">
                  <UI.Content className="flex flex-wrap items-center gap-2 text-sm">
                    <UI.Text as="span" className="text-muted-foreground">
                      {beijingTime(post.published_at)}
                    </UI.Text>
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
                  </UI.Content>
                  {post.translation_zh && (
                    <UI.Text className="leading-7 whitespace-pre-wrap">
                      {post.translation_zh}
                    </UI.Text>
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
                        <UI.Text as="span" className="min-w-0 text-left">
                          原文与上下文
                        </UI.Text>
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
                      <UI.Text className="mt-3 leading-7 whitespace-pre-wrap">
                        {post.text}
                      </UI.Text>
                      {post.context.map((context) => (
                        <UI.Quote
                          key={`${context.relation}-${context.id}`}
                          className="bg-muted/40 mt-3 rounded-lg p-4"
                        >
                          <UI.Text className="text-muted-foreground mb-2">
                            {context.relation === "reply"
                              ? "回复上下文"
                              : "引用上下文"}{" "}
                            · {context.author}
                          </UI.Text>
                          <UI.Text className="leading-6 whitespace-pre-wrap">
                            {context.text_zh ?? context.original_text}
                          </UI.Text>
                          <Button asChild variant="link" className="px-0">
                            <UI.TextLink
                              href={context.url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              阅读上下文原帖
                            </UI.TextLink>
                          </Button>
                        </UI.Quote>
                      ))}
                    </CollapsibleContent>
                  </Collapsible>
                  <Button asChild variant="link" className="px-0">
                    <UI.TextLink
                      href={post.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      阅读源帖子
                    </UI.TextLink>
                  </Button>
                </ItemContent>
              </Item>
            ))}
          </ItemGroup>
        </>
      )}
      <UI.Content className="flex flex-wrap items-center gap-3">
        <Button
          variant="outline"
          disabled={page === 1 || state.status !== "ready"}
          onClick={() => move(-1)}
        >
          上一页帖子
        </Button>
        <UI.Text as="span" className="text-muted-foreground text-sm">
          第 {page} 页，每页最多 50 条
        </UI.Text>
        <Button
          variant="outline"
          disabled={
            state.status !== "ready" || state.posts.length < 50 || page >= 1000
          }
          onClick={() => move(1)}
        >
          下一页帖子
        </Button>
      </UI.Content>
    </UI.Content>
  );
}

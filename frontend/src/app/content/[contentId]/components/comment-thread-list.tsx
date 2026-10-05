"use client";
import * as UI from "@/components/ui/content";

import { toast } from "sonner";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDownIcon, ExternalLinkIcon, RotateCcwIcon } from "lucide-react";

import { listContentComments } from "@/api/zuopinziliao";
import { CommentRefreshAction } from "@/app/content/[contentId]/components/comment-refresh-action";
import {
  formatMetric,
  formatTime,
  safeExternalHref,
} from "@/app/content/components/content-presenters";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Empty, EmptyDescription } from "@/components/ui/empty";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/request";

type CommentPageState =
  | { status: "loading" }
  | { status: "error"; message: string; requestId?: string }
  | {
      status: "ready";
      items: HotKeyAPI.ContentCommentView[];
      nextCursor: string | null;
    };

function toError(
  error: unknown,
): Extract<CommentPageState, { status: "error" }> {
  return error instanceof ApiRequestError
    ? { status: "error", message: error.message, requestId: error.requestId }
    : { status: "error", message: "评论读取失败，请稍后重试。" };
}

function useCommentPage(postId: string, rootId: string | null) {
  const [state, setState] = useState<CommentPageState>({ status: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);
  const loadingMoreRef = useRef(false);
  const request = useRef<AbortController | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const fetchPage = useCallback(
    (cursor?: string, signal?: AbortSignal) =>
      listContentComments(
        {
          content_id: postId,
          root_id: rootId ?? undefined,
          cursor,
          limit: 20,
        },
        { signal },
      ),
    [postId, rootId],
  );

  useEffect(() => {
    const controller = new AbortController();
    request.current = controller;
    void fetchPage(undefined, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        setState({
          status: "ready",
          items: page.items,
          nextCursor: page.next_cursor,
        });
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (controller.signal.aborted) return;

        const failure = toError(error);
        toast.error(failure.message, {
          description: failure.requestId
            ? `请求编号：${failure.requestId}`
            : undefined,
        });
        setState(failure);
      });
    return () => controller.abort();
  }, [fetchPage, reloadToken]);

  function reload() {
    request.current?.abort();
    loadingMoreRef.current = false;
    setLoadingMore(false);
    setState({ status: "loading" });
    setReloadToken((value) => value + 1);
  }

  async function loadMore() {
    if (
      state.status !== "ready" ||
      state.nextCursor === null ||
      loadingMoreRef.current
    )
      return;
    const controller = request.current;
    if (!controller || controller.signal.aborted) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    try {
      const page = await fetchPage(state.nextCursor, controller.signal);
      if (controller.signal.aborted) return;
      setState({
        status: "ready",
        items: [...state.items, ...page.items],
        nextCursor: page.next_cursor,
      });
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (controller.signal.aborted) return;
      const failure = toError(error);
      toast.error(failure.message, {
        description: failure.requestId
          ? `请求编号：${failure.requestId}`
          : undefined,
      });
    } finally {
      if (controller.signal.aborted) return;
      loadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }

  return { state, reload, loadMore, loadingMore };
}

export function parentRelationLabel(
  status: HotKeyAPI.ContentCommentView["parent_relation_status"],
): string | null {
  if (status === "unavailable") return "直接父评论无正文或不可读";
  if (status === "unresolved") return "父链尚未确认";
  return null;
}

export function replyContext(
  comment: HotKeyAPI.ContentCommentView,
  root: HotKeyAPI.ContentCommentView,
  visible: ReadonlyMap<string, HotKeyAPI.ContentCommentView>,
): string | null {
  if (comment.parent_content_id === root.content_id) {
    return root.external_id ? `回复线程根 ${root.external_id}` : "回复线程根";
  }
  const parent = comment.parent_content_id
    ? visible.get(comment.parent_content_id)
    : undefined;
  if (parent?.external_id) return `回复 ${parent.external_id}`;
  return comment.parent_relation_status === "observed"
    ? "直接父评论未在本页显示"
    : null;
}

export function CommentCard({
  comment,
  context,
}: {
  comment: HotKeyAPI.ContentCommentView;
  context?: string | null;
}) {
  const observation = comment.latest_observation;
  const version = observation?.content_version;
  const body = version?.body ?? version?.title;
  const externalHref = safeExternalHref(observation?.canonical_url ?? null);
  const relationNotice = parentRelationLabel(comment.parent_relation_status);

  return (
    <UI.Content as="article" className="py-4">
      <UI.Content className="flex flex-wrap items-center gap-2">
        <Badge variant={observation ? "secondary" : "outline"}>
          {observation ? "已保存评论" : "关系占位"}
        </Badge>
        {relationNotice ? (
          <Badge variant="outline">{relationNotice}</Badge>
        ) : null}
        {observation ? (
          <UI.Text as="span" className="text-muted-foreground text-xs">
            观察于 {formatTime(observation.observed_at)}
          </UI.Text>
        ) : null}
      </UI.Content>
      {body ? (
        <UI.Text className="mt-3 leading-7 break-words whitespace-pre-wrap">
          {body}
        </UI.Text>
      ) : (
        <UI.Text className="text-muted-foreground mt-3 text-sm">
          {observation
            ? "未取得评论正文"
            : "此节点暂无可读正文，保留其线程关系。"}
        </UI.Text>
      )}
      {context ? (
        <UI.Text className="text-muted-foreground mt-2 text-xs">
          {context}
        </UI.Text>
      ) : null}
      {observation ? (
        <UI.Text className="text-muted-foreground mt-3 text-xs">
          作者 {observation.author_external_id ?? "未知"} · 点赞{" "}
          {formatMetric(observation.metrics.like_count)}
        </UI.Text>
      ) : null}
      {externalHref ? (
        <UI.TextLink
          className="mt-3 inline-flex items-center gap-1 text-sm underline underline-offset-4"
          href={externalHref}
          target="_blank"
          rel="noreferrer"
        >
          打开原评论
          <ExternalLinkIcon className="size-3" aria-hidden="true" />
        </UI.TextLink>
      ) : null}
    </UI.Content>
  );
}

function PageNotice({
  state,
  onRetry,
  emptyText,
}: {
  state: CommentPageState;
  onRetry: () => void;
  emptyText: string;
}) {
  if (state.status === "loading") {
    return (
      <UI.Text className="text-muted-foreground mt-4 text-sm">
        正在读取已保存评论…
      </UI.Text>
    );
  }
  if (state.status === "error") {
    return (
      <Alert variant="destructive" className="mt-4">
        <AlertTitle>评论读取失败</AlertTitle>
        <AlertDescription>请重新加载已保存评论。</AlertDescription>
        <Button
          type="button"
          variant="secondary"
          className="mt-3"
          onClick={onRetry}
        >
          <RotateCcwIcon data-icon="inline-start" />
          重新加载
        </Button>
      </Alert>
    );
  }
  return state.items.length === 0 ? (
    <Empty className="mt-6">
      <EmptyDescription>{emptyText}</EmptyDescription>
    </Empty>
  ) : null;
}

function MoreButton({
  cursor,
  loading,
  onClick,
}: {
  cursor: string | null;
  loading: boolean;
  onClick: () => void;
}) {
  return (
    <UI.Content className="mt-4">
      {cursor ? (
        <Button
          type="button"
          variant="outline"
          disabled={loading}
          onClick={onClick}
        >
          {loading ? "正在加载…" : "加载更多已保存评论"}
        </Button>
      ) : null}
    </UI.Content>
  );
}

function CommentBranch({
  postId,
  root,
}: {
  postId: string;
  root: HotKeyAPI.ContentCommentView;
}) {
  const page = useCommentPage(postId, root.content_id);
  const visible = new Map(
    page.state.status === "ready"
      ? page.state.items.map((item) => [item.content_id, item] as const)
      : [],
  );
  return (
    <UI.Content className="mt-3 flex flex-col gap-6 pl-3 sm:pl-6">
      <PageNotice
        state={page.state}
        onRetry={() => void page.reload()}
        emptyText="暂无可读回复；这不表示来源评论已全部取完。"
      />
      {page.state.status === "ready"
        ? page.state.items.map((item) => (
            <CommentCard
              key={item.content_id}
              comment={item}
              context={replyContext(item, root, visible)}
            />
          ))
        : null}
      {page.state.status === "ready" ? (
        <MoreButton
          cursor={page.state.nextCursor}
          loading={page.loadingMore}
          onClick={() => void page.loadMore()}
        />
      ) : null}
    </UI.Content>
  );
}

function CommentRoot({
  postId,
  root,
}: {
  postId: string;
  root: HotKeyAPI.ContentCommentView;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <Collapsible open={expanded} onOpenChange={setExpanded}>
      <CommentCard comment={root} />
      {root.has_replies ? (
        <CollapsibleTrigger asChild>
          <Button type="button" variant="ghost" size="sm" className="mt-2">
            {expanded ? "收起回复" : "查看已保存回复"}
            <ChevronDownIcon data-icon="inline-end" />
          </Button>
        </CollapsibleTrigger>
      ) : null}
      <CollapsibleContent>
        {expanded ? <CommentBranch postId={postId} root={root} /> : null}
      </CollapsibleContent>
    </Collapsible>
  );
}

export function CommentThreadList({ postId }: { postId: string }) {
  const page = useCommentPage(postId, null);
  return (
    <UI.Content
      as="section"
      aria-labelledby="comments-heading"
      className="mt-10"
    >
      <UI.Heading
        level={2}
        id="comments-heading"
        className="text-xl font-medium"
      >
        已保存评论
      </UI.Heading>
      <UI.Text className="text-muted-foreground mt-2 text-sm leading-6">
        按线程根阅读本地仍可读的评论。父链缺口会保留；本地分页结束不代表来源尾段已核对。
      </UI.Text>
      <CommentRefreshAction postId={postId} />
      <PageNotice
        state={page.state}
        onRetry={() => void page.reload()}
        emptyText="暂无可读评论；当前为空不代表来源没有评论。"
      />
      {page.state.status === "ready" ? (
        <UI.Content className="mt-6 flex flex-col gap-8">
          {page.state.items.map((root) => (
            <CommentRoot key={root.content_id} postId={postId} root={root} />
          ))}
        </UI.Content>
      ) : null}
      {page.state.status === "ready" ? (
        <MoreButton
          cursor={page.state.nextCursor}
          loading={page.loadingMore}
          onClick={() => void page.loadMore()}
        />
      ) : null}
    </UI.Content>
  );
}

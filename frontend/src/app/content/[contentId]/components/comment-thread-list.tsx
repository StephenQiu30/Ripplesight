"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ExternalLinkIcon, RotateCcwIcon } from "lucide-react";

import { listContentComments } from "@/api/zuopinziliao";
import { CommentRefreshAction } from "@/app/content/[contentId]/components/comment-refresh-action";
import {
  formatMetric,
  formatTime,
  safeExternalHref,
} from "@/app/content/components/content-presenters";
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
  const router = useRouter();
  const [state, setState] = useState<CommentPageState>({ status: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);
  const loadingMoreRef = useRef(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);

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
    void fetchPage(undefined, controller.signal)
      .then((page) => {
        setState({
          status: "ready",
          items: page.items,
          nextCursor: page.next_cursor,
        });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (
          error instanceof ApiRequestError &&
          error.code === "invalid_session"
        ) {
          router.replace("/login");
          return;
        }
        setState(toError(error));
      });
    return () => controller.abort();
  }, [fetchPage, router]);

  async function reload() {
    setState({ status: "loading" });
    try {
      const page = await fetchPage();
      setState({
        status: "ready",
        items: page.items,
        nextCursor: page.next_cursor,
      });
    } catch (error) {
      if (
        error instanceof ApiRequestError &&
        error.code === "invalid_session"
      ) {
        router.replace("/login");
      } else {
        setState(toError(error));
      }
    }
  }

  async function loadMore() {
    if (
      state.status !== "ready" ||
      state.nextCursor === null ||
      loadingMoreRef.current
    )
      return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const page = await fetchPage(state.nextCursor);
      setState({
        status: "ready",
        items: [...state.items, ...page.items],
        nextCursor: page.next_cursor,
      });
    } catch (error) {
      if (
        error instanceof ApiRequestError &&
        error.code === "invalid_session"
      ) {
        router.replace("/login");
      } else {
        setLoadMoreError(toError(error).message);
      }
    } finally {
      loadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }

  return { state, reload, loadMore, loadingMore, loadMoreError };
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
    <article className="bg-muted rounded-2xl p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={observation ? "secondary" : "outline"}>
          {observation ? "已保存评论" : "关系占位"}
        </Badge>
        {relationNotice ? (
          <Badge variant="outline">{relationNotice}</Badge>
        ) : null}
        {observation ? (
          <span className="text-muted-foreground text-xs">
            观察于 {formatTime(observation.observed_at)}
          </span>
        ) : null}
      </div>
      {body ? (
        <p className="mt-3 leading-7 break-words whitespace-pre-wrap">{body}</p>
      ) : (
        <p className="text-muted-foreground mt-3 text-sm">
          {observation
            ? "未取得评论正文"
            : "此节点暂无可读正文，保留其线程关系。"}
        </p>
      )}
      {context ? (
        <p className="text-muted-foreground mt-2 text-xs">{context}</p>
      ) : null}
      {observation ? (
        <p className="text-muted-foreground mt-3 text-xs">
          作者 {observation.author_external_id ?? "未知"} · 点赞{" "}
          {formatMetric(observation.metrics.like_count)}
        </p>
      ) : null}
      {externalHref ? (
        <a
          className="mt-3 inline-flex items-center gap-1 text-sm underline underline-offset-4"
          href={externalHref}
          target="_blank"
          rel="noreferrer"
        >
          打开原评论
          <ExternalLinkIcon className="size-3" aria-hidden="true" />
        </a>
      ) : null}
    </article>
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
      <p className="text-muted-foreground mt-4 text-sm">正在读取已保存评论…</p>
    );
  }
  if (state.status === "error") {
    return (
      <div className="bg-destructive/10 mt-4 rounded-2xl p-5">
        <p role="alert" className="text-sm">
          {state.message}
          {state.requestId ? ` 请求编号：${state.requestId}` : null}
        </p>
        <Button
          type="button"
          variant="secondary"
          className="mt-3"
          onClick={onRetry}
        >
          <RotateCcwIcon data-icon="inline-start" />
          重新加载
        </Button>
      </div>
    );
  }
  return state.items.length === 0 ? (
    <p className="text-muted-foreground mt-4 text-sm">{emptyText}</p>
  ) : null;
}

function MoreButton({
  cursor,
  loading,
  error,
  onClick,
}: {
  cursor: string | null;
  loading: boolean;
  error: string | null;
  onClick: () => void;
}) {
  return (
    <div className="mt-4">
      {error ? (
        <p role="alert" className="text-destructive mb-2 text-sm">
          {error}
        </p>
      ) : null}
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
    </div>
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
    <div className="mt-3 space-y-3 pl-3 sm:pl-6">
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
          error={page.loadMoreError}
          onClick={() => void page.loadMore()}
        />
      ) : null}
    </div>
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
    <div>
      <CommentCard comment={root} />
      {root.has_replies ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="mt-2"
          aria-expanded={expanded}
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? "收起回复" : "查看已保存回复"}
        </Button>
      ) : null}
      {expanded ? <CommentBranch postId={postId} root={root} /> : null}
    </div>
  );
}

export function CommentThreadList({ postId }: { postId: string }) {
  const page = useCommentPage(postId, null);
  return (
    <section aria-labelledby="comments-heading" className="mt-10">
      <h2 id="comments-heading" className="text-xl font-medium">
        已保存评论
      </h2>
      <p className="text-muted-foreground mt-2 text-sm leading-6">
        按线程根阅读本地仍可读的评论。父链缺口会保留；本地分页结束不代表来源尾段已核对。
      </p>
      <CommentRefreshAction postId={postId} />
      <PageNotice
        state={page.state}
        onRetry={() => void page.reload()}
        emptyText="暂无可读评论；当前为空不代表来源没有评论。"
      />
      {page.state.status === "ready" ? (
        <div className="mt-4 space-y-4">
          {page.state.items.map((root) => (
            <CommentRoot key={root.content_id} postId={postId} root={root} />
          ))}
        </div>
      ) : null}
      {page.state.status === "ready" ? (
        <MoreButton
          cursor={page.state.nextCursor}
          loading={page.loadingMore}
          error={page.loadMoreError}
          onClick={() => void page.loadMore()}
        />
      ) : null}
    </section>
  );
}

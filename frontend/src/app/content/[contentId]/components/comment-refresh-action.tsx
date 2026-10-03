"use client";

import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { RotateCcwIcon } from "lucide-react";

import {
  getContentCommentRunReadiness,
  runContentComments,
} from "@/api/zuopinziliao";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/request";

type RefreshState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      readiness: HotKeyAPI.CommentRunReadinessView;
    }
  | { status: "accepted"; jobId: string };

export class CommentRefreshOperation {
  private operationId: string | null = null;
  private pending = false;
  private accepted = false;

  constructor(
    private readonly newId: () => string = () => crypto.randomUUID(),
  ) {}

  begin(): string | null {
    if (this.pending || this.accepted) return null;
    this.pending = true;
    this.operationId ??= this.newId();
    return this.operationId;
  }

  finish(accepted: boolean): void {
    this.pending = false;
    this.accepted = accepted;
  }
}

export function commentRefreshReason(
  reason: HotKeyAPI.CommentRunReadinessView["reason"],
): string {
  if (reason === "comments_rate_limited")
    return "同一作品的评论更新仍在间隔期内，请稍后再试。";
  if (reason === "comments_budget_exhausted")
    return "评论请求预算已用尽，请在预算恢复后再试。";
  return "当前来源或主题暂不允许更新评论。";
}

export function CommentRefreshControls({
  readiness,
  submitting,
  onRefresh,
}: {
  readiness: HotKeyAPI.CommentRunReadinessView;
  submitting: boolean;
  onRefresh: () => void;
}) {
  if (!readiness.supported) return null;
  return (
    <div className="mt-4">
      {readiness.supported ? (
        <Button
          type="button"
          variant="outline"
          disabled={!readiness.available || submitting}
          onClick={onRefresh}
        >
          <RotateCcwIcon data-icon="inline-start" />
          {submitting ? "正在受理…" : "更新评论"}
        </Button>
      ) : null}
      {readiness.reason ? (
        <p role="status" className="text-muted-foreground mt-2 text-sm">
          {commentRefreshReason(readiness.reason)}
        </p>
      ) : null}
    </div>
  );
}

export function CommentRefreshAction({ postId }: { postId: string }) {
  return <CommentRefreshActionContent key={postId} postId={postId} />;
}

function CommentRefreshActionContent({ postId }: { postId: string }) {
  const router = useRouter();
  const operation = useRef(new CommentRefreshOperation());
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const [state, setState] = useState<RefreshState>({ status: "loading" });
  const [submitting, setSubmitting] = useState(false);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void getContentCommentRunReadiness(
      { content_id: postId },
      { signal: controller.signal },
    )
      .then((readiness) => {
        if (!controller.signal.aborted)
          setState({ status: "ready", readiness });
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (controller.signal.aborted) return;

        toast.error(
          error instanceof ApiRequestError
            ? `${error.message}${error.requestId ? ` 请求编号：${error.requestId}` : ""}`
            : "评论更新资格暂不可用，请重试。",
        );
        setState({ status: "error", message: "请重新加载评论更新资格。" });
      });
    return () => controller.abort();
  }, [postId, retryToken]);

  async function refresh() {
    if (state.status !== "ready" || !state.readiness.available) return;
    const operationId = operation.current.begin();
    if (!operationId) return;
    setSubmitting(true);
    try {
      const accepted = await runContentComments(
        { content_id: postId },
        { operation_id: operationId },
      );
      operation.current.finish(true);
      if (!mounted.current) return;
      setState({ status: "accepted", jobId: accepted.job_id });
      router.push(`/jobs/${accepted.job_id}`);
    } catch (error) {
      operation.current.finish(false);
      if (
        !mounted.current ||
        (error instanceof ApiRequestError && error.kind === "cancelled")
      )
        return;

      if (
        error instanceof ApiRequestError &&
        (error.code === "comments_rate_limited" ||
          error.code === "comments_budget_exhausted" ||
          error.code === "comments_not_ready")
      ) {
        setState({
          status: "ready",
          readiness: {
            supported: error.code !== "comments_not_ready",
            available: false,
            reason: error.code,
          },
        });
        toast.error(commentRefreshReason(error.code));
      } else {
        setState({ status: "ready", readiness: state.readiness });
        toast.error(
          error instanceof ApiRequestError
            ? `${error.message}。可使用同一次操作标识重试。`
            : "更新请求未确认，可使用同一次操作标识重试。",
        );
      }
    } finally {
      if (mounted.current) setSubmitting(false);
    }
  }

  if (state.status === "loading") return null;
  if (state.status === "error") {
    return (
      <div className="mt-4 flex flex-col items-start gap-3">
        <Alert variant="destructive">
          <AlertDescription>{state.message}</AlertDescription>
        </Alert>
        <Button
          variant="outline"
          onClick={() => {
            setState({ status: "loading" });
            setRetryToken((value) => value + 1);
          }}
        >
          <RotateCcwIcon data-icon="inline-start" />
          重试
        </Button>
      </div>
    );
  }
  if (state.status === "accepted") {
    return (
      <p role="status" className="mt-4 text-sm">
        评论更新已受理。
        <Link className="underline" href={`/jobs/${state.jobId}`}>
          查看采集任务
        </Link>
      </p>
    );
  }
  return (
    <CommentRefreshControls
      readiness={state.readiness}
      submitting={submitting}
      onRefresh={() => void refresh()}
    />
  );
}

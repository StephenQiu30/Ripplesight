"use client";

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
      message: string | null;
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
  message,
  onRefresh,
}: {
  readiness: HotKeyAPI.CommentRunReadinessView;
  submitting: boolean;
  message: string | null;
  onRefresh: () => void;
}) {
  if (!readiness.supported && !message) return null;
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
      {readiness.reason || message ? (
        <p role="status" className="text-muted-foreground mt-2 text-sm">
          {message ?? commentRefreshReason(readiness.reason)}
        </p>
      ) : null}
    </div>
  );
}

export function CommentRefreshAction({ postId }: { postId: string }) {
  const router = useRouter();
  const operation = useRef(new CommentRefreshOperation());
  const [state, setState] = useState<RefreshState>({ status: "loading" });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void getContentCommentRunReadiness(
      { content_id: postId },
      { signal: controller.signal },
    )
      .then((readiness) =>
        setState({ status: "ready", readiness, message: null }),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (
          error instanceof ApiRequestError &&
          error.code === "invalid_session"
        ) {
          router.replace("/login");
          return;
        }
        setState({
          status: "error",
          message: "评论更新资格暂不可用，请重新加载页面。",
        });
      });
    return () => controller.abort();
  }, [postId, router]);

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
      setState({ status: "accepted", jobId: accepted.job_id });
      router.push(`/jobs/${accepted.job_id}`);
    } catch (error) {
      operation.current.finish(false);
      if (
        error instanceof ApiRequestError &&
        error.code === "invalid_session"
      ) {
        router.replace("/login");
        return;
      }
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
          message: commentRefreshReason(error.code),
        });
      } else {
        setState({
          status: "ready",
          readiness: state.readiness,
          message:
            error instanceof ApiRequestError
              ? `${error.message}。可使用同一次操作标识重试。`
              : "更新请求未确认，可使用同一次操作标识重试。",
        });
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (state.status === "loading") return null;
  if (state.status === "error") {
    return (
      <p role="alert" className="text-destructive mt-4 text-sm">
        {state.message}
      </p>
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
      message={state.message}
      onRefresh={() => void refresh()}
    />
  );
}

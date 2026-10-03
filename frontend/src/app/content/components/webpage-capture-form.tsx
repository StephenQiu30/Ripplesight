"use client";

import { toast } from "sonner";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { ArrowRightIcon, LoaderCircleIcon } from "lucide-react";

import { createCollectionJob } from "@/api/caijirenwu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { ApiRequestError } from "@/request";

type SubmissionError = {
  message: string;
  requestId?: string;
};

type PendingOperation = {
  operationId: string;
  target: string;
};

export function validateWebPageTarget(target: string): string | null {
  if (target.length === 0) {
    return "请输入要采集的网页地址。";
  }
  try {
    const url = new URL(target);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return "请输入完整的 http:// 或 https:// 地址。";
    }
    return url.username || url.password
      ? "网页地址不能包含用户名或密码。"
      : null;
  } catch {
    return "请输入完整的 http:// 或 https:// 地址。";
  }
}

export function resolvePendingOperation(
  current: PendingOperation | null,
  target: string,
  createId: () => string,
): PendingOperation {
  return current?.target === target
    ? current
    : { operationId: createId(), target };
}

function toSubmissionError(error: unknown): SubmissionError {
  return error instanceof ApiRequestError
    ? { message: error.message, requestId: error.requestId }
    : { message: "网页采集任务提交失败，请稍后重试。" };
}

export function WebPageCaptureForm() {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const router = useRouter();
  const [target, setTarget] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isSubmittingRef = useRef(false);
  const pendingOperationRef = useRef<PendingOperation | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current) {
      return;
    }

    const normalizedTarget = target.trim();
    const validationError = validateWebPageTarget(normalizedTarget);
    if (validationError) {
      setFieldError(validationError);
      toast.error(validationError);
      event.currentTarget
        .querySelector<HTMLInputElement>("#webpage-url")
        ?.focus();
      return;
    }

    const pendingOperation = resolvePendingOperation(
      pendingOperationRef.current,
      normalizedTarget,
      () => crypto.randomUUID(),
    );
    pendingOperationRef.current = pendingOperation;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setFieldError(null);

    try {
      const job = await createCollectionJob({
        operation_id: pendingOperation.operationId,
        kind: "webpage.collect",
        url: normalizedTarget,
      });
      if (mounted.current) router.push(`/jobs/${job.job_id}`);
    } catch (error) {
      if (!mounted.current) return;
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      const failure = toSubmissionError(error);
      toast.error(failure.message, {
        description: failure.requestId
          ? `请求编号：${failure.requestId}`
          : undefined,
      });
    } finally {
      isSubmittingRef.current = false;
      if (mounted.current) setIsSubmitting(false);
    }
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="max-w-3xl">
        <h2 className="text-lg font-medium">添加网页</h2>
        <p className="text-muted-foreground mt-2 text-sm leading-6">
          提交当前允许范围内的公开网页。系统会创建后台任务，完成后可从任务页打开已保存资料。
        </p>
      </div>

      <form
        className="flex flex-col gap-5"
        noValidate
        onSubmit={(event) => void handleSubmit(event)}
      >
        <FieldGroup>
          <Field
            data-invalid={Boolean(fieldError)}
            data-disabled={isSubmitting}
          >
            <FieldLabel htmlFor="webpage-url">网页地址</FieldLabel>
            <Input
              id="webpage-url"
              name="url"
              type="url"
              inputMode="url"
              autoComplete="url"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="https://example.com/article"
              value={target}
              onChange={(event) => {
                const nextTarget = event.target.value;
                setTarget(nextTarget);
                setFieldError(null);
                if (pendingOperationRef.current?.target !== nextTarget.trim()) {
                  pendingOperationRef.current = null;
                }
              }}
              aria-invalid={fieldError ? true : undefined}
              disabled={isSubmitting}
              required
            />
            <FieldDescription>
              提交后进入任务页查看受理状态，受理不表示已采集完成。
            </FieldDescription>
          </Field>
          <Button
            type="submit"
            size="lg"
            className="sm:min-w-28"
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <>
                <LoaderCircleIcon
                  data-icon="inline-start"
                  className="animate-spin"
                />
                正在提交
              </>
            ) : (
              <>
                创建任务
                <ArrowRightIcon data-icon="inline-end" />
              </>
            )}
          </Button>
        </FieldGroup>
      </form>
    </section>
  );
}

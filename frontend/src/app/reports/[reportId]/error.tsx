"use client";

import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <PageState
      state="error"
      eyebrow="报告阅读"
      title="暂时无法读取报告"
      description="请重新尝试读取。"
      errorCode={error.digest ?? "report_render_failed"}
      action={<Button onClick={reset}>重新读取</Button>}
    />
  );
}

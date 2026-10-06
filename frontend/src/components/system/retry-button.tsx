"use client";

import { RotateCwIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { Button } from "@/components/ui/button";

// 默认的重试：重新请求当前路由的服务端数据，请求期间按钮忙碌、不能重复点击。
export function RetryButton() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <Button
      onClick={() => startTransition(() => router.refresh())}
      disabled={pending}
      aria-busy={pending || undefined}
    >
      <RotateCwIcon data-icon="inline-start" aria-hidden="true" />
      重试
    </Button>
  );
}

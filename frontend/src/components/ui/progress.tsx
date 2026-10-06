"use client";

import * as React from "react";
import { cn } from "cn";
import { Progress as ProgressPrimitive } from "radix-ui";

function Progress({
  className,
  value,
  ...props
}: React.ComponentProps<typeof ProgressPrimitive.Root>) {
  // 生产环境 CSP 不允许服务端渲染的 style 属性，位移在客户端经 CSSOM 设置。
  const indicator = React.useRef<HTMLDivElement>(null);
  React.useLayoutEffect(() => {
    indicator.current?.style.setProperty(
      "translate",
      `-${100 - (value || 0)}% 0`,
    );
  }, [value]);
  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      value={value}
      className={cn(
        "bg-muted relative flex h-1 w-full items-center overflow-x-hidden rounded-full",
        className,
      )}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        ref={indicator}
        className="bg-primary size-full flex-1 -translate-x-full transition-all motion-reduce:transition-none"
      />
    </ProgressPrimitive.Root>
  );
}

export { Progress };

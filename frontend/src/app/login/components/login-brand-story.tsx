import type { ReactNode } from "react";
import Image from "next/image";
import * as UI from "@/components/ui/content";
import { Skeleton } from "@/components/ui/skeleton";

export function LoginBrandStory({ children }: { children?: ReactNode }) {
  return (
    <UI.Content
      as="aside"
      aria-label="Ripplesight"
      className="hidden min-w-0 flex-col gap-8 lg:flex"
    >
      <Image
        src="/brand/login-ripple.png"
        alt=""
        aria-hidden="true"
        width={1717}
        height={916}
        sizes="556px"
        loading="eager"
        className="h-login-art w-full object-cover"
      />
      <UI.Content layout="stack" className="gap-4">
        <UI.Heading level={2} appearance="display">
          知微见澜
        </UI.Heading>
        <UI.Text tone="muted" size="lead">
          沿着各平台的 AI
          热点，看清发生了什么、讨论如何变化。登录后设置监控主题，跟踪来源、进展与告警。
        </UI.Text>
      </UI.Content>
      <UI.Content layout="stack" className="gap-2">
        <UI.Text tone="muted" size="xs">
          正在发生
        </UI.Text>
        {children ?? <Skeleton className="h-28 w-full" />}
      </UI.Content>
    </UI.Content>
  );
}

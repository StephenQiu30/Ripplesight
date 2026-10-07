import * as UI from "@/components/ui/content";
import Image from "next/image";

import { BrandLockup } from "@/components/brand/brand-lockup";
import { Button } from "@/components/ui/button";

export function LoginBrandStory() {
  return (
    <UI.Content
      as="aside"
      className="mx-auto flex w-full max-w-md min-w-0 flex-col items-start gap-3 lg:max-w-none lg:gap-8"
      aria-label="Ripplesight"
    >
      <BrandLockup href="/" />
      <Image
        src="/brand/login-ripple.png"
        alt=""
        aria-hidden="true"
        width={1717}
        height={916}
        sizes="(min-width: 1280px) 576px, (min-width: 1024px) 448px, 1px"
        loading="eager"
        className="hidden h-auto w-full lg:block"
      />
      <UI.Text tone="muted" className="hidden lg:block">
        读有出处的 AI 资讯，登录后跟踪你关心的主题。
      </UI.Text>
      <Button asChild variant="link" size="sm" className="justify-start px-0">
        <UI.TextLink href="/">不登录，先看今日热点</UI.TextLink>
      </Button>
    </UI.Content>
  );
}

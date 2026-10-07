import type { ReactNode } from "react";
import * as UI from "@/components/ui/content";
import { BrandLockup } from "@/components/brand/brand-lockup";
import { Button } from "@/components/ui/button";
import { LoginBrandStory } from "./login-brand-story";

export function LoginExperience({
  children,
  liveStories,
}: {
  children: ReactNode;
  liveStories?: ReactNode;
}) {
  return (
    <UI.Content className="login-page flex min-w-0 flex-col">
      <UI.Content
        as="header"
        className="flex min-h-16 items-center justify-between gap-4 px-4 md:px-8"
      >
        <BrandLockup href="/" bilingual />
        <Button asChild variant="link" size="sm">
          <UI.TextLink href="/">不登录，先看今日热点</UI.TextLink>
        </Button>
      </UI.Content>
      <UI.Content className="login-columns max-w-login mx-auto grid w-full min-w-0 flex-1 items-center gap-8 px-4 py-8 lg:gap-16 lg:px-0 lg:py-20">
        <LoginBrandStory>{liveStories}</LoginBrandStory>
        {children}
      </UI.Content>
    </UI.Content>
  );
}

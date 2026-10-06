import * as UI from "@/components/ui/content";
import type { Metadata } from "next";
import { connection } from "next/server";
import { headers } from "next/headers";

import { safeReturnTo } from "@/components/auth/access";
import { LoginExperience } from "./components/login-experience";
import { LoginForm } from "./components/login-form";
import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "登录",
  description: "登录知微见澜，进入你的信息监控工作区。",
  robots: { index: false, follow: false },
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{
    returnTo?: string;
    return_to?: string;
    next?: string;
    error?: string;
  }>;
}) {
  await connection();
  const params = await searchParams;
  const returnTo = safeReturnTo(
    params.returnTo ?? params.return_to ?? params.next,
  );
  if ((await headers()).get("x-hotkey-session-error") === "1")
    return (
      <PageState
        state="error"
        eyebrow="服务暂时不可用"
        title="暂时无法验证登录状态"
        description="登录服务暂时无法响应。你的会话没有被退出，请稍后重新加载。"
        action={
          <Button asChild>
            <UI.TextLink href={returnTo}>重新加载</UI.TextLink>
          </Button>
        }
      />
    );
  return (
    <LoginExperience>
      <LoginForm returnTo={returnTo} oauthFailed={!!params.error} />
    </LoginExperience>
  );
}

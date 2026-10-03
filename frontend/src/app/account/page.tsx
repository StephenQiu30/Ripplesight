import type { Metadata } from "next";
import { connection } from "next/server";

import { readLayoutSession } from "@/components/auth/layout-session";
import { safeReturnTo } from "@/components/auth/access";
import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";
import { AccountSettings } from "./components/account-settings";

export const metadata: Metadata = {
  title: "账户设置",
  robots: { index: false, follow: false },
};

export default async function AccountPage({
  searchParams,
}: {
  searchParams: Promise<{
    setup?: string;
    returnTo?: string;
    error?: string;
    linked?: string;
  }>;
}) {
  await connection();
  const params = await searchParams;
  const returnTo = safeReturnTo(params.returnTo);
  const loginReturnTo = params.setup === "1" ? returnTo : "/account";
  const session = await readLayoutSession();
  if (!session)
    return (
      <PageState
        eyebrow="登录"
        title="请重新登录"
        description="验证当前会话后可以修改账户设置。"
        action={
          <Button asChild>
            <a href={`/login?returnTo=${encodeURIComponent(loginReturnTo)}`}>
              登录
            </a>
          </Button>
        }
      />
    );
  return (
    <AccountSettings
      key={session.expires_at}
      session={session}
      initialSetup={params.setup === "1" && !session.user.has_password}
      returnTo={returnTo}
      oauthError={params.error}
      githubLinked={params.linked === "github" && session.user.github_connected}
    />
  );
}

import type { Metadata } from "next";
import { connection } from "next/server";

import { readLayoutSession } from "@/components/auth/layout-session";
import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";
import { CredentialsForm } from "./components/credentials-form";

export const metadata: Metadata = {
  title: "账户设置",
  robots: { index: false, follow: false },
};

export default async function AccountPage() {
  await connection();
  const session = await readLayoutSession();
  if (!session)
    return (
      <PageState
        eyebrow="登录"
        title="请重新登录"
        description="验证当前会话后可以修改账户设置。"
        action={
          <Button asChild>
            <a href="/login?returnTo=%2Faccount">登录</a>
          </Button>
        }
      />
    );
  return <CredentialsForm session={session} />;
}

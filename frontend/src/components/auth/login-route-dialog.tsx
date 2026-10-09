"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { LoginDialog } from "./login-dialog";

export function LoginRouteDialog({
  returnTo,
  oauthFailed,
  errorContent,
}: {
  returnTo: string;
  oauthFailed: boolean;
  errorContent?: ReactNode;
}) {
  const router = useRouter();
  return (
    <LoginDialog
      open
      returnTo={returnTo}
      oauthFailed={oauthFailed}
      errorContent={errorContent}
      onClose={() => router.replace("/")}
      onRestoreFocus={() =>
        document.getElementById("page-content")?.focus({ preventScroll: true })
      }
    />
  );
}

"use client";

import dynamic from "next/dynamic";
import type { ReactNode } from "react";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { LoginFormSkeleton } from "@/app/login/components/login-form-layout";

const LoginForm = dynamic(
  () =>
    import("@/app/login/components/login-form").then(
      (module) => module.LoginForm,
    ),
  { loading: () => <LoginFormSkeleton /> },
);

export function LoginDialog({
  open,
  onClose,
  returnTo,
  oauthFailed = false,
  errorContent,
  onAuthenticated,
  onRestoreFocus,
}: {
  open: boolean;
  onClose: () => void;
  returnTo: string;
  oauthFailed?: boolean;
  errorContent?: ReactNode;
  onAuthenticated?: () => void;
  onRestoreFocus?: () => void;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value) onClose();
      }}
    >
      <DialogContent
        className="max-h-[calc(100dvh-2rem)] max-w-md overflow-y-auto p-6 sm:p-8"
        onCloseAutoFocus={
          onRestoreFocus
            ? (event) => {
                event.preventDefault();
                onRestoreFocus();
              }
            : undefined
        }
      >
        <DialogHeader>
          <DialogTitle className="text-2xl">登录 Ripplesight</DialogTitle>
          <DialogDescription>
            公开资讯无需登录。登录后可保存关键词、配置平台和查看个人监控结果。
          </DialogDescription>
        </DialogHeader>
        {errorContent ?? (
          <LoginForm
            returnTo={returnTo}
            oauthFailed={oauthFailed}
            embedded
            onAuthenticated={onAuthenticated}
          />
        )}
        <DialogClose asChild>
          <Button variant="ghost" className="w-full">
            暂不登录，继续浏览
          </Button>
        </DialogClose>
      </DialogContent>
    </Dialog>
  );
}

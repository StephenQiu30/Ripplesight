"use client";
import * as UI from "@/components/ui/content";

import { Item } from "@/components/ui/item";

import { CheckCircle2Icon, ChevronRightIcon, UploadIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import { toast } from "sonner";

import { updateIdentityProfile, uploadIdentityAvatar } from "@/api/identity";
import { authErrorMessage } from "@/components/auth/auth-error";
import { UserAvatar } from "@/components/auth/user-avatar";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiRequestError } from "@/request";
import { CredentialsForm } from "./credentials-form";
import { ReportEmailSubscription } from "./report-email-subscription";
import { IdentityConnections } from "./identity-connections";

function readImage(file: File, signal: AbortSignal): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    const abort = () => reader.abort();
    signal.addEventListener("abort", abort, { once: true });
    reader.onloadend = () => signal.removeEventListener("abort", abort);
    reader.onload = () => {
      if (typeof reader.result === "string")
        resolve(reader.result.split(",")[1]);
      else reject(new Error("Image read failed"));
    };
    reader.onerror = () => reject(new Error("Image read failed"));
    reader.onabort = () => reject(new Error("Image read aborted"));
    if (signal.aborted) reject(new Error("Image read aborted"));
    else reader.readAsDataURL(file);
  });
}

export function AccountSettings({
  session,
  initialSetup = false,
  returnTo,
  oauthError,
  githubLinked = false,
}: {
  session: HotKeyAPI.IdentitySessionView;
  initialSetup?: boolean;
  returnTo?: string;
  oauthError?: string;
  githubLinked?: boolean;
}) {
  const router = useRouter();
  const [account, setAccount] = useState(session);
  const [username, setUsername] = useState(session.user.username);
  const [tab, setTab] = useState("security");
  const [busy, setBusy] = useState<"avatar" | "profile" | null>(null);
  const [credentialsBusy, setCredentialsBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const operation = useRef<AbortController | null>(null);
  useEffect(() => () => operation.current?.abort(), []);

  async function mutate(
    kind: "avatar" | "profile",
    action: (signal: AbortSignal) => Promise<HotKeyAPI.IdentitySessionView>,
  ) {
    if (busy || credentialsBusy) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy(kind);
    try {
      const updated = await action(controller.signal);
      if (controller.signal.aborted) return;
      setAccount(updated);
      setUsername(updated.user.username);
      toast.success(kind === "avatar" ? "头像已更新。" : "个人资料已保存。");
      router.refresh();
    } catch (failure) {
      if (!controller.signal.aborted) {
        toast.error(
          failure instanceof ApiRequestError &&
            failure.code === "username_unavailable"
            ? "此用户名已被使用，请换一个。"
            : authErrorMessage(
                failure,
                kind === "avatar"
                  ? "头像上传失败，请重试。"
                  : "资料保存失败，请重试。",
              ),
        );
      }
    } finally {
      if (operation.current === controller) {
        operation.current = null;
        setBusy(null);
      }
    }
  }

  function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || busy || credentialsBusy) return;
    if (
      !["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
      file.size === 0 ||
      file.size > 2 * 1024 * 1024
    ) {
      toast.error("请选择 JPG、PNG 或 WebP 图片，最大 2 MB。");
      return;
    }
    void mutate("avatar", async (signal) =>
      uploadIdentityAvatar(
        {
          mime: file.type as HotKeyAPI.IdentityAvatarInput["mime"],
          data_base64: await readImage(file, signal),
        },
        { signal },
      ),
    );
  }

  function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$/.test(username)) {
      toast.error("用户名需要 3–64 个字母、数字或 . _ -，以字母或数字开头。");
      return;
    }
    void mutate("profile", (signal) =>
      updateIdentityProfile({ username }, { signal }),
    );
  }

  if (initialSetup)
    return (
      <UI.Content className="flex flex-col gap-12">
        <CredentialsForm session={session} initialSetup returnTo={returnTo} />
        <IdentityConnections
          session={session}
          oauthError={oauthError}
          githubLinked={githubLinked}
        />
      </UI.Content>
    );
  const disabled = !!busy || credentialsBusy;
  return (
    <UI.Content
      as="section"
      aria-labelledby="account-title"
      className="flex w-full flex-col gap-8"
    >
      <UI.Content as="header" className="flex flex-col gap-3">
        <UI.Heading
          level={1}
          id="account-title"
          className="text-3xl font-medium tracking-tight sm:text-4xl"
        >
          账户设置
        </UI.Heading>
        <UI.Text className="text-muted-foreground text-sm leading-6">
          让资料与登录方式保持最新。
        </UI.Text>
      </UI.Content>
      <UI.Content className="flex flex-col items-stretch gap-8 lg:flex-row lg:items-start lg:gap-12">
        <Item variant="muted" className="bg-muted items-stretch" asChild>
          <UI.Content
            as="aside"
            aria-label="个人资料"
            className="flex flex-col gap-8 p-6 sm:px-8 sm:py-10 lg:w-1/3 lg:shrink-0"
          >
            <UI.Content className="flex flex-col items-center gap-5">
              <UserAvatar
                user={account.user}
                className="size-32 sm:size-36"
                retryable
              />
              <UI.Text className="max-w-full text-center text-xl font-medium break-all">
                {account.user.username}
              </UI.Text>
              <UI.Content className="flex flex-col items-center gap-3">
                <Input
                  ref={fileInput}
                  id="account-avatar"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  aria-label="上传头像文件"
                  className="sr-only"
                  tabIndex={-1}
                  disabled={disabled}
                  onChange={upload}
                />
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11"
                  disabled={disabled}
                  onClick={() => fileInput.current?.click()}
                >
                  <UploadIcon aria-hidden="true" data-icon="inline-start" />
                  {busy === "avatar"
                    ? "正在上传…"
                    : account.user.avatar_sha256
                      ? "更换头像"
                      : "上传头像"}
                </Button>
                <UI.Text className="text-muted-foreground text-center text-xs leading-5">
                  JPG、PNG 或 WebP，最大 2 MB。
                </UI.Text>
              </UI.Content>
            </UI.Content>
            <Separator />
            <UI.Content as="dl" className="grid grid-cols-1 gap-5 text-sm">
              <UI.Content className="flex flex-col gap-2 sm:flex-row sm:gap-4 lg:flex-col xl:flex-row">
                <UI.Content as="dt" className="text-muted-foreground shrink-0">
                  用户名
                </UI.Content>
                <UI.Content as="dd" className="min-w-0 break-all">
                  {account.user.username}
                </UI.Content>
              </UI.Content>
              <UI.Content className="flex flex-col gap-2 sm:flex-row sm:gap-4 lg:flex-col xl:flex-row">
                <UI.Content as="dt" className="text-muted-foreground shrink-0">
                  邮箱
                </UI.Content>
                <UI.Content as="dd" className="min-w-0 break-all">
                  {account.user.email || "尚未绑定"}
                </UI.Content>
              </UI.Content>
              {account.user.email && (
                <UI.Content className="flex items-center gap-4">
                  <UI.Content as="dt" className="text-muted-foreground">
                    验证状态
                  </UI.Content>
                  <UI.Content as="dd" className="flex items-center gap-2">
                    <CheckCircle2Icon className="size-4" aria-hidden="true" />
                    已验证
                  </UI.Content>
                </UI.Content>
              )}
            </UI.Content>
            <Separator />
            <Button
              type="button"
              variant="link"
              className="min-h-11 justify-start self-start p-0"
              disabled={disabled}
              onClick={() => setTab("profile")}
            >
              编辑资料
              <ChevronRightIcon aria-hidden="true" data-icon="inline-end" />
            </Button>
          </UI.Content>
        </Item>
        <Tabs
          value={tab}
          onValueChange={setTab}
          className="min-w-0 gap-8 lg:flex-1"
        >
          <TabsList
            variant="line"
            className="border-border h-11 w-full justify-start gap-6 border-b"
          >
            <TabsTrigger
              value="profile"
              className="flex-none px-0 text-base"
              disabled={disabled}
            >
              基本资料
            </TabsTrigger>
            <TabsTrigger
              value="security"
              className="flex-none px-0 text-base"
              disabled={disabled}
            >
              登录安全
            </TabsTrigger>
            <TabsTrigger
              value="notifications"
              className="flex-none px-0 text-base"
              disabled={disabled}
            >
              报告通知
            </TabsTrigger>
          </TabsList>
          <TabsContent value="notifications">
            <ReportEmailSubscription />
          </TabsContent>
          <TabsContent
            value="profile"
            forceMount
            className="data-[state=inactive]:hidden"
          >
            <UI.Form
              aria-label="编辑个人资料"
              onSubmit={saveProfile}
              className="flex max-w-xl flex-col gap-8"
            >
              <UI.Content as="header" className="flex flex-col gap-3">
                <UI.Heading level={2} className="text-2xl font-medium">
                  基本资料
                </UI.Heading>
                <UI.Text className="text-muted-foreground text-sm leading-6">
                  更新用户名，也可用于登录当前账户。
                </UI.Text>
              </UI.Content>
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="profile-username">用户名</FieldLabel>
                  <Input
                    id="profile-username"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    autoComplete="username"
                    autoCapitalize="none"
                    spellCheck={false}
                    required
                    minLength={3}
                    maxLength={64}
                    pattern="[A-Za-z0-9][A-Za-z0-9._-]{2,63}"
                    disabled={disabled}
                  />
                  <FieldDescription>
                    3–64 个字母、数字或 . _ -，以字母或数字开头。
                  </FieldDescription>
                </Field>
                <Button
                  type="submit"
                  className="min-h-11 self-start"
                  disabled={disabled || username === account.user.username}
                >
                  {busy === "profile" ? "正在保存…" : "保存资料"}
                </Button>
              </FieldGroup>
            </UI.Form>
          </TabsContent>
          <TabsContent
            value="security"
            forceMount
            className="flex flex-col gap-10 data-[state=inactive]:hidden"
          >
            <CredentialsForm
              key={account.user.username}
              session={account}
              embedded
              disabled={!!busy}
              onBusyChange={setCredentialsBusy}
              onUpdated={setAccount}
            />
            <IdentityConnections
              session={account}
              oauthError={oauthError}
              githubLinked={githubLinked}
            />
          </TabsContent>
        </Tabs>
      </UI.Content>
    </UI.Content>
  );
}

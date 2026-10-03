"use client";
import { Alert, AlertDescription } from "@/components/ui/alert";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { EyeIcon, EyeOffIcon, KeyRoundIcon, MailIcon } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";

import {
  createIdentitySession,
  getLoginOptions,
  sendEmailLoginCode,
  startGithubLogin,
  verifyEmailLoginCode,
} from "@/api/identity";
import { safeReturnTo } from "@/components/auth/access";
import { authErrorMessage } from "@/components/auth/auth-error";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Empty,
  EmptyContent,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Separator } from "@/components/ui/separator";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group";
import { LoginFormLayout, LoginFormSkeleton } from "./login-form-layout";

type LoginMethod = "password" | "email" | "github";

export function LoginForm({
  returnTo,
  oauthFailed = false,
}: {
  returnTo: string;
  oauthFailed?: boolean;
}) {
  const router = useRouter();
  const [options, setOptions] = useState<HotKeyAPI.LoginOptionsView | null>(
    null,
  );
  const [optionError, setOptionError] = useState(false);
  const [reload, setReload] = useState(0);
  const [method, setMethod] = useState<LoginMethod>("password");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] =
    useState<HotKeyAPI.EmailChallengeView | null>(null);
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(0);
  const [busy, setBusy] = useState<LoginMethod | "email-code" | null>(null);
  const feedbackId = useId();
  const oauthNoticeShown = useRef(false);
  const operation = useRef<AbortController | null>(null);
  const credentialInput = useRef<HTMLInputElement | null>(null);
  const focusNextMethod = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    getLoginOptions({ signal: controller.signal })
      .then((value) => {
        if (controller.signal.aborted) return;
        setOptions(value);
        setOptionError(false);
        setMethod(
          value.password ? "password" : value.email ? "email" : "github",
        );
      })
      .catch((failure) => {
        if (!controller.signal.aborted) {
          setOptionError(true);
          toast.error(authErrorMessage(failure, "登录方式读取失败，请重试。"), {
            id: feedbackId,
          });
        }
      });
    return () => controller.abort();
  }, [reload, feedbackId]);

  useEffect(() => {
    if (oauthFailed && !oauthNoticeShown.current) {
      oauthNoticeShown.current = true;
      toast.error("GitHub 登录未完成，请重新尝试。", { id: feedbackId });
    }
  }, [oauthFailed, feedbackId]);

  useEffect(() => {
    if (!challenge) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [challenge]);

  useEffect(() => () => operation.current?.abort(), []);

  useEffect(() => {
    if (!focusNextMethod.current) return;
    focusNextMethod.current = false;
    credentialInput.current?.focus();
  }, [method]);

  function enterWorkspace() {
    router.replace(safeReturnTo(returnTo));
    router.refresh();
  }

  async function run(
    kind: NonNullable<typeof busy>,
    action: (signal: AbortSignal) => Promise<void>,
  ) {
    if (busy) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy(kind);
    toast.dismiss(feedbackId);
    try {
      await action(controller.signal);
    } catch (failure) {
      if (!controller.signal.aborted)
        toast.error(authErrorMessage(failure, "登录未完成，请重试。"), {
          id: feedbackId,
        });
    } finally {
      if (operation.current === controller) {
        operation.current = null;
        setBusy(null);
      }
    }
  }

  function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run("password", async (signal) => {
      await createIdentitySession({ username, password }, { signal });
      if (signal.aborted) return;
      setPassword("");
      enterWorkspace();
    });
  }

  function sendCode() {
    void run("email-code", async (signal) => {
      const next = await sendEmailLoginCode({ email }, { signal });
      if (signal.aborted) return;
      const sentAt = Date.now();
      setChallenge(next);
      setCode("");
      setNow(sentAt);
      setResendAt(sentAt + next.resend_after_seconds * 1000);
    });
  }

  function submitEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!challenge || now >= Date.parse(challenge.expires_at)) {
      sendCode();
      return;
    }
    void run("email", async (signal) => {
      const session = await verifyEmailLoginCode(
        { challenge_id: challenge.challenge_id, code },
        { signal },
      );
      if (signal.aborted) return;
      setCode("");
      if (!session.user.has_password) {
        router.replace(
          `/account?setup=1&returnTo=${encodeURIComponent(safeReturnTo(returnTo))}`,
        );
        router.refresh();
      } else {
        enterWorkspace();
      }
    });
  }

  function githubLogin() {
    void run("github", async (signal) => {
      const result = await startGithubLogin(
        { return_to: safeReturnTo(returnTo) },
        { signal },
      );
      if (!signal.aborted) window.location.assign(result.authorization_url);
    });
  }

  const wait = Math.max(0, Math.ceil((resendAt - now) / 1000));
  const expired = !!challenge && now >= Date.parse(challenge.expires_at);
  const ready = !!options && !busy;

  function changeMethod(next: "password" | "email") {
    focusNextMethod.current = true;
    setMethod(next);
    setShowPassword(false);
    toast.dismiss(feedbackId);
  }

  return (
    <LoginFormLayout loading={!options && !optionError}>
      {!options && !optionError && <LoginFormSkeleton />}
      {optionError && (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>登录方式暂时不可用</EmptyTitle>
          </EmptyHeader>
          <EmptyContent>
            <Button
              variant="outline"
              onClick={() => {
                toast.dismiss(feedbackId);
                setOptionError(false);
                setReload((value) => value + 1);
              }}
            >
              重新读取
            </Button>
          </EmptyContent>
        </Empty>
      )}
      {options && (
        <>
          {method === "password" && options.password && (
            <form onSubmit={submitPassword} aria-label="账号密码登录">
              <FieldGroup className="gap-6">
                <Field data-disabled={!ready}>
                  <FieldLabel htmlFor="login-username">邮箱或用户名</FieldLabel>
                  <Input
                    ref={credentialInput}
                    id="login-username"
                    name="username"
                    autoComplete="username"
                    autoCapitalize="none"
                    spellCheck={false}
                    required
                    minLength={3}
                    maxLength={254}
                    placeholder="输入邮箱或用户名"
                    className="h-12 px-4"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    disabled={!ready}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="login-password">密码</FieldLabel>
                  <InputGroup className="h-12">
                    <InputGroupInput
                      id="login-password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="current-password"
                      required
                      maxLength={128}
                      placeholder="输入密码"
                      className="h-full pl-4"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      disabled={!ready}
                    />
                    <InputGroupAddon align="inline-end">
                      <InputGroupButton
                        aria-label={showPassword ? "隐藏密码" : "显示密码"}
                        aria-pressed={showPassword}
                        aria-controls="login-password"
                        size="icon-sm"
                        className="size-10"
                        disabled={!ready}
                        onClick={() => setShowPassword((value) => !value)}
                      >
                        {showPassword ? (
                          <EyeOffIcon aria-hidden="true" />
                        ) : (
                          <EyeIcon aria-hidden="true" />
                        )}
                      </InputGroupButton>
                    </InputGroupAddon>
                  </InputGroup>
                </Field>
                <Button
                  type="submit"
                  size="lg"
                  className="h-12 w-full"
                  disabled={!ready}
                >
                  {busy === "password" ? "正在登录…" : "登录并进入工作区"}
                </Button>
              </FieldGroup>
            </form>
          )}
          {method === "email" && options.email && (
            <form onSubmit={submitEmail} aria-label="邮箱验证码登录">
              <FieldGroup className="gap-6">
                <Field data-disabled={!ready}>
                  <FieldLabel htmlFor="login-email">邮箱</FieldLabel>
                  <Input
                    ref={credentialInput}
                    id="login-email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    autoCapitalize="none"
                    required
                    maxLength={254}
                    placeholder="输入邮箱地址"
                    className="h-12 px-4"
                    value={email}
                    onChange={(event) => {
                      setEmail(event.target.value);
                      setChallenge(null);
                      setCode("");
                      toast.dismiss(feedbackId);
                    }}
                    disabled={!ready}
                  />
                  <FieldDescription>
                    首次使用此邮箱？验证后设置密码，即可使用邮箱和密码登录。
                  </FieldDescription>
                </Field>
                {challenge && (
                  <Field data-disabled={!ready || expired}>
                    <FieldLabel htmlFor="login-code">验证码</FieldLabel>
                    <Input
                      id="login-code"
                      name="code"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      pattern="[0-9]{6}"
                      required
                      minLength={6}
                      maxLength={6}
                      placeholder="输入 6 位验证码"
                      className="h-12 px-4"
                      value={code}
                      onChange={(event) => setCode(event.target.value)}
                      disabled={!ready || expired}
                    />
                    <FieldDescription role="status">
                      {expired
                        ? "验证码已过期，请重新发送。"
                        : "验证码已发送，请查看邮箱。"}
                    </FieldDescription>
                  </Field>
                )}
                <Button
                  type="submit"
                  size="lg"
                  className="h-12 w-full"
                  disabled={!ready || (expired && wait > 0)}
                >
                  {busy === "email-code"
                    ? "正在发送…"
                    : busy === "email"
                      ? "正在验证…"
                      : challenge && !expired
                        ? "验证并继续"
                        : "发送验证码"}
                </Button>
                {challenge && (
                  <Button
                    type="button"
                    variant="ghost"
                    className="min-h-11"
                    disabled={!ready || wait > 0}
                    onClick={sendCode}
                  >
                    {wait ? `${wait} 秒后可重新发送` : "重新发送验证码"}
                  </Button>
                )}
              </FieldGroup>
            </form>
          )}
          {method === "github" && (
            <Alert role="status" className="leading-6">
              <AlertDescription>请选择下方可用的登录方式。</AlertDescription>
            </Alert>
          )}
          <div
            className="mt-7 flex flex-col gap-y-3"
            role="group"
            aria-label="其他登录方式"
          >
            <div className="text-muted-foreground mb-4 flex items-center gap-4 text-xs">
              <Separator className="flex-1" />
              <span>或使用其他方式</span>
              <Separator className="flex-1" />
            </div>
            <Button
              type="button"
              variant="outline"
              size="lg"
              className="h-12 w-full gap-3"
              disabled={
                !ready ||
                !(method === "email" ? options.password : options.email)
              }
              onClick={() =>
                changeMethod(method === "email" ? "password" : "email")
              }
            >
              {method === "email" ? (
                <KeyRoundIcon aria-hidden="true" className="size-5" />
              ) : (
                <MailIcon aria-hidden="true" className="size-5" />
              )}
              {method === "email" ? "使用账号密码登录" : "使用邮箱验证码登录"}
            </Button>
            {method === "email" && !options.password && (
              <p className="text-muted-foreground text-xs leading-5">
                账号密码登录暂未启用。
              </p>
            )}
            {method !== "email" && !options.email && (
              <p className="text-muted-foreground text-xs leading-5">
                邮箱验证码登录尚未配置。
              </p>
            )}
            <Button
              type="button"
              variant="outline"
              size="lg"
              className="h-12 w-full gap-3"
              disabled={!ready || !options.github}
              onClick={githubLogin}
            >
              <Image
                src="/brand/github-mark.png"
                alt=""
                aria-hidden="true"
                width={28}
                height={28}
                className="size-7 dark:invert"
              />
              {busy === "github" ? "正在前往 GitHub…" : "使用 GitHub 登录"}
            </Button>
            {!options.github && (
              <p className="text-muted-foreground text-xs leading-5">
                GitHub 登录尚未配置。
              </p>
            )}
          </div>
        </>
      )}
    </LoginFormLayout>
  );
}

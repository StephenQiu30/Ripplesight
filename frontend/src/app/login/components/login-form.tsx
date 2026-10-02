"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ExternalLinkIcon } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

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
  const [optionError, setOptionError] = useState("");
  const [reload, setReload] = useState(0);
  const [method, setMethod] = useState<LoginMethod>("password");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] =
    useState<HotKeyAPI.EmailChallengeView | null>(null);
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(0);
  const [busy, setBusy] = useState<LoginMethod | "email-code" | null>(null);
  const [error, setError] = useState(
    oauthFailed ? "GitHub 登录未完成，请重新尝试。" : "",
  );
  const operation = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getLoginOptions({ signal: controller.signal })
      .then((value) => {
        if (controller.signal.aborted) return;
        setOptions(value);
        setOptionError("");
        setMethod(
          value.password ? "password" : value.email ? "email" : "github",
        );
      })
      .catch((failure) => {
        if (!controller.signal.aborted)
          setOptionError(
            authErrorMessage(failure, "登录方式读取失败，请重试。"),
          );
      });
    return () => controller.abort();
  }, [reload]);

  useEffect(() => {
    if (!challenge) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [challenge]);

  useEffect(() => () => operation.current?.abort(), []);

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
    setError("");
    try {
      await action(controller.signal);
    } catch (failure) {
      if (!controller.signal.aborted)
        setError(authErrorMessage(failure, "登录未完成，请重试。"));
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
      await verifyEmailLoginCode(
        { challenge_id: challenge.challenge_id, code },
        { signal },
      );
      if (signal.aborted) return;
      setCode("");
      enterWorkspace();
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

  return (
    <section
      aria-labelledby="login-title"
      className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-8"
    >
      <div className="mb-9 space-y-3">
        <h1 id="login-title" className="text-3xl font-light tracking-tight">
          登录知微见澜
        </h1>
        <p className="text-muted-foreground text-sm leading-6">
          继续关注你在意的，沿着来源看见变化。
        </p>
      </div>
      {!options && !optionError && (
        <p role="status" className="text-muted-foreground text-sm">
          正在读取登录方式…
        </p>
      )}
      {optionError && (
        <div className="space-y-3">
          <p role="alert" className="text-destructive text-sm">
            {optionError}
          </p>
          <Button
            variant="outline"
            onClick={() => {
              setOptionError("");
              setReload((value) => value + 1);
            }}
          >
            重新读取
          </Button>
        </div>
      )}
      {options && (
        <Tabs
          value={method}
          onValueChange={(value) => {
            setMethod(value as LoginMethod);
            setError("");
          }}
        >
          <TabsList variant="line" className="mb-7 grid w-full grid-cols-3">
            <TabsTrigger value="password" disabled={!!busy}>
              账号密码
            </TabsTrigger>
            <TabsTrigger value="email" disabled={!!busy}>
              邮箱验证码
            </TabsTrigger>
            <TabsTrigger value="github" disabled={!!busy}>
              GitHub
            </TabsTrigger>
          </TabsList>
          <TabsContent value="password">
            {options.password ? (
              <form onSubmit={submitPassword} aria-label="账号密码登录">
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="login-username">用户名</FieldLabel>
                    <Input
                      id="login-username"
                      name="username"
                      autoComplete="username"
                      autoCapitalize="none"
                      spellCheck={false}
                      required
                      minLength={3}
                      maxLength={64}
                      value={username}
                      onChange={(event) => setUsername(event.target.value)}
                      disabled={!ready}
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="login-password">密码</FieldLabel>
                    <Input
                      id="login-password"
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      required
                      maxLength={128}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      disabled={!ready}
                    />
                  </Field>
                  <Button type="submit" size="lg" disabled={!ready}>
                    {busy === "password" ? "正在登录…" : "登录并进入系统"}
                  </Button>
                </FieldGroup>
              </form>
            ) : (
              <p className="text-muted-foreground text-sm leading-6">
                账号密码登录暂未启用，请选择其他登录方式。
              </p>
            )}
          </TabsContent>
          <TabsContent value="email">
            {options.email ? (
              <form onSubmit={submitEmail} aria-label="邮箱验证码登录">
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="login-email">邮箱</FieldLabel>
                    <Input
                      id="login-email"
                      name="email"
                      type="email"
                      autoComplete="email"
                      autoCapitalize="none"
                      required
                      maxLength={254}
                      value={email}
                      onChange={(event) => {
                        setEmail(event.target.value);
                        setChallenge(null);
                        setCode("");
                        setError("");
                      }}
                      disabled={!ready}
                    />
                  </Field>
                  {challenge && (
                    <Field>
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
                    disabled={!ready || (expired && wait > 0)}
                  >
                    {busy === "email-code"
                      ? "正在发送…"
                      : busy === "email"
                        ? "正在验证…"
                        : challenge && !expired
                          ? "验证并进入系统"
                          : "发送验证码"}
                  </Button>
                  {challenge && (
                    <Button
                      type="button"
                      variant="ghost"
                      disabled={!ready || wait > 0}
                      onClick={sendCode}
                    >
                      {wait ? `${wait} 秒后可重新发送` : "重新发送验证码"}
                    </Button>
                  )}
                </FieldGroup>
              </form>
            ) : (
              <p className="text-muted-foreground text-sm leading-6">
                邮箱验证码登录尚未配置，请选择其他登录方式。
              </p>
            )}
          </TabsContent>
          <TabsContent value="github">
            <div className="space-y-5">
              <p className="text-muted-foreground text-sm leading-6">
                使用 GitHub 账户登录，授权完成后返回你的工作区。
              </p>
              {options.github ? (
                <Button
                  size="lg"
                  className="w-full"
                  disabled={!ready}
                  onClick={githubLogin}
                >
                  <ExternalLinkIcon />
                  {busy === "github" ? "正在前往 GitHub…" : "使用 GitHub 登录"}
                </Button>
              ) : (
                <p className="text-muted-foreground text-sm leading-6">
                  GitHub 登录尚未配置，请选择其他登录方式。
                </p>
              )}
            </div>
          </TabsContent>
        </Tabs>
      )}
      {error && (
        <p role="alert" className="text-destructive mt-5 text-sm leading-6">
          {error}
        </p>
      )}
      {busy && (
        <Button
          variant="ghost"
          className="mt-3 self-start"
          onClick={() => {
            operation.current?.abort();
            setError("请求已取消，可以重新操作。");
          }}
        >
          取消
        </Button>
      )}
      <p className="text-muted-foreground mt-9 text-xs leading-6">
        登录即表示你已阅读
        <Link
          href="/terms"
          className="text-foreground underline underline-offset-4"
        >
          使用条款
        </Link>
        与
        <Link
          href="/privacy"
          className="text-foreground underline underline-offset-4"
        >
          隐私说明
        </Link>
        。
      </p>
    </section>
  );
}

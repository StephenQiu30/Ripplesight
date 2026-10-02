"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { sendEmailLoginCode, updateIdentityCredentials } from "@/api/identity";
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
import { ApiRequestError } from "@/request";

export function CredentialsForm({
  session,
  initialSetup = false,
  returnTo = "/topics",
}: {
  session: HotKeyAPI.IdentitySessionView;
  initialSetup?: boolean;
  returnTo?: string;
}) {
  const router = useRouter();
  const [account, setAccount] = useState(session);
  const [username, setUsername] = useState(session.user.username);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [verification, setVerification] = useState<
    "recent" | "password" | "email"
  >(session.user.has_password ? "password" : "recent");
  const [challenge, setChallenge] =
    useState<HotKeyAPI.EmailChallengeView | null>(null);
  const [code, setCode] = useState("");
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(0);
  const [busy, setBusy] = useState<"save" | "send" | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const operation = useRef<AbortController | null>(null);
  const hasPassword = account.user.has_password;

  useEffect(() => () => operation.current?.abort(), []);
  useEffect(() => {
    if (!challenge) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [challenge]);

  async function sendCode() {
    if (busy || !account.user.email) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy("send");
    setError("");
    setSuccess("");
    try {
      const value = await sendEmailLoginCode(
        { email: account.user.email },
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      const sentAt = Date.now();
      setChallenge(value);
      setCode("");
      setNow(sentAt);
      setResendAt(sentAt + value.resend_after_seconds * 1000);
    } catch (failure) {
      if (!controller.signal.aborted)
        setError(authErrorMessage(failure, "验证码发送失败，请重试。"));
    } finally {
      if (operation.current === controller) {
        operation.current = null;
        setBusy(null);
      }
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setSuccess("");
    if (password !== confirmation) {
      setError("两次输入的新密码不一致。");
      return;
    }
    if (password.length < 12 || password.length > 128) {
      setError("密码需要 12–128 个字符。");
      return;
    }
    if (verification === "password" && !currentPassword) {
      setError("请输入当前密码，或使用邮箱验证码验证。");
      return;
    }
    if (
      verification === "email" &&
      (!challenge ||
        now >= Date.parse(challenge.expires_at) ||
        !/^[0-9]{6}$/.test(code))
    ) {
      setError("请发送并填写有效的邮箱验证码。");
      return;
    }
    const controller = new AbortController();
    operation.current = controller;
    setBusy("save");
    setError("");
    try {
      const updated = await updateIdentityCredentials(
        {
          username,
          password,
          current_password:
            verification === "password" ? currentPassword : undefined,
          challenge_id:
            verification === "email" ? challenge?.challenge_id : undefined,
          code: verification === "email" ? code : undefined,
        },
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setPassword("");
      setCurrentPassword("");
      setConfirmation("");
      setCode("");
      setChallenge(null);
      setAccount(updated);
      setUsername(updated.user.username);
      setVerification("password");
      if (initialSetup && !hasPassword) {
        router.replace(safeReturnTo(returnTo));
      } else {
        setSuccess(
          "密码已保存。下次可使用邮箱或用户名和密码登录。其他设备的旧会话已退出。",
        );
      }
      router.refresh();
    } catch (failure) {
      if (!controller.signal.aborted) {
        if (
          failure instanceof ApiRequestError &&
          failure.code === "credentials_verification_required" &&
          !hasPassword &&
          account.user.email
        ) {
          setVerification("email");
          setChallenge(null);
          setCode("");
          setError("登录验证已过期，请重新验证下方已绑定邮箱后设置密码。");
        } else {
          setError(authErrorMessage(failure, "账户设置保存失败，请重试。"));
        }
      }
    } finally {
      if (operation.current === controller) {
        operation.current = null;
        setBusy(null);
      }
    }
  }

  const wait = Math.max(0, Math.ceil((resendAt - now) / 1000));
  const expired = !!challenge && now >= Date.parse(challenge.expires_at);
  const emailVerification = (
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor="account-code">邮箱验证码</FieldLabel>
        <Input
          id="account-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          required={verification === "email"}
          minLength={6}
          maxLength={6}
          pattern="[0-9]{6}"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          disabled={!!busy || !challenge || expired}
        />
        <FieldDescription role="status">
          {expired
            ? "验证码已过期，请重新发送。"
            : challenge
              ? "验证码已发送至当前已验证邮箱。"
              : "验证码会发送至当前已验证邮箱。"}
        </FieldDescription>
      </Field>
      <Button
        type="button"
        variant="outline"
        className="min-h-11 self-start"
        disabled={!!busy || wait > 0}
        onClick={() => void sendCode()}
      >
        {busy === "send"
          ? "正在发送…"
          : wait
            ? `${wait} 秒后可重新发送`
            : challenge
              ? "重新发送验证码"
              : "发送验证码"}
      </Button>
    </FieldGroup>
  );

  return (
    <section
      aria-labelledby="account-title"
      className="w-full max-w-xl space-y-8"
    >
      <header className="space-y-3">
        {!hasPassword && account.user.email && (
          <p className="text-muted-foreground text-sm">
            邮箱已验证 · 设置登录密码
          </p>
        )}
        <h1 id="account-title" className="text-3xl font-medium tracking-tight">
          {hasPassword ? "账户设置" : "设置登录密码"}
        </h1>
        <p className="text-muted-foreground text-sm leading-6">
          {hasPassword
            ? "修改密码后，当前设备保持登录，其他设备的旧会话将退出。"
            : "为账户设置密码。以后可以直接使用已验证邮箱和密码登录。"}
        </p>
        {account.user.email && (
          <p className="text-muted-foreground text-sm break-all">
            已验证邮箱：{account.user.email}
          </p>
        )}
      </header>
      <form onSubmit={submit} aria-label="设置登录凭据">
        <FieldGroup>
          {hasPassword && (
            <Field>
              <FieldLabel htmlFor="account-username">用户名</FieldLabel>
              <Input
                id="account-username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                minLength={3}
                maxLength={64}
                pattern="[a-z0-9][a-z0-9._-]{2,63}"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                disabled={!!busy}
              />
              <FieldDescription>
                3–64 个小写字母、数字或 . _ -，以字母或数字开头。
              </FieldDescription>
            </Field>
          )}
          <Field>
            <FieldLabel htmlFor="account-password">新密码</FieldLabel>
            <Input
              id="account-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              maxLength={128}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={!!busy}
            />
            <FieldDescription>使用 12–128 个字符。</FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="account-confirmation">确认新密码</FieldLabel>
            <Input
              id="account-confirmation"
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              maxLength={128}
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              disabled={!!busy}
            />
          </Field>
          {hasPassword && (
            <Tabs
              value={verification}
              onValueChange={(value) => {
                setVerification(value as "password" | "email");
                setError("");
              }}
            >
              {account.user.email && (
                <TabsList variant="line" className="mb-4">
                  <TabsTrigger value="password" disabled={!!busy}>
                    当前密码
                  </TabsTrigger>
                  <TabsTrigger value="email" disabled={!!busy}>
                    邮箱验证码
                  </TabsTrigger>
                </TabsList>
              )}
              <TabsContent value="password">
                <Field>
                  <FieldLabel htmlFor="account-current-password">
                    当前密码
                  </FieldLabel>
                  <Input
                    id="account-current-password"
                    type="password"
                    autoComplete="current-password"
                    required={verification === "password"}
                    maxLength={128}
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                    disabled={!!busy}
                  />
                  <FieldDescription>
                    输入当前密码，或使用已验证邮箱的验证码确认修改。
                  </FieldDescription>
                </Field>
              </TabsContent>
              {account.user.email && (
                <TabsContent value="email">{emailVerification}</TabsContent>
              )}
            </Tabs>
          )}
          {!hasPassword && verification === "email" && emailVerification}
          {!hasPassword && verification === "recent" && account.user.email && (
            <Button
              type="button"
              variant="ghost"
              className="min-h-11 self-start"
              disabled={!!busy}
              onClick={() => {
                setVerification("email");
                setError("");
              }}
            >
              重新验证邮箱
            </Button>
          )}
          {error && (
            <p role="alert" className="text-destructive text-sm leading-6">
              {error}
            </p>
          )}
          {success && (
            <p role="status" className="text-sm leading-6">
              {success}
            </p>
          )}
          <Button
            type="submit"
            className="min-h-11 self-start"
            disabled={!!busy}
          >
            {busy === "save"
              ? "正在保存…"
              : initialSetup && !hasPassword
                ? "设置密码并进入工作区"
                : "保存密码"}
          </Button>
          {busy && (
            <Button
              type="button"
              variant="ghost"
              className="min-h-11 self-start"
              onClick={() => {
                operation.current?.abort();
                setError("请求已取消，可以重新操作。");
              }}
            >
              取消
            </Button>
          )}
        </FieldGroup>
      </form>
    </section>
  );
}

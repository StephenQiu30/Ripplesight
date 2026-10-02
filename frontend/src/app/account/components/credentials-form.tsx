"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { sendEmailLoginCode, updateIdentityCredentials } from "@/api/identity";
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

export function CredentialsForm({
  session,
}: {
  session: HotKeyAPI.IdentitySessionView;
}) {
  const router = useRouter();
  const [username, setUsername] = useState(session.user.username);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [verification, setVerification] = useState("password");
  const [challenge, setChallenge] =
    useState<HotKeyAPI.EmailChallengeView | null>(null);
  const [code, setCode] = useState("");
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(0);
  const [busy, setBusy] = useState<"save" | "send" | null>(null);
  const [error, setError] = useState("");
  const operation = useRef<AbortController | null>(null);

  useEffect(() => () => operation.current?.abort(), []);
  useEffect(() => {
    if (!challenge) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [challenge]);

  async function sendCode() {
    if (busy || !session.user.email) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy("send");
    setError("");
    try {
      const value = await sendEmailLoginCode(
        { email: session.user.email },
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
    if (password !== confirmation) {
      setError("两次输入的新密码不一致。");
      return;
    }
    if (
      verification === "email" &&
      (!challenge || now >= Date.parse(challenge.expires_at))
    ) {
      setError("请发送并填写有效的邮箱验证码。");
      return;
    }
    const controller = new AbortController();
    operation.current = controller;
    setBusy("save");
    setError("");
    try {
      await updateIdentityCredentials(
        {
          username,
          password,
          current_password:
            verification === "password" && currentPassword
              ? currentPassword
              : undefined,
          challenge_id:
            verification === "email" ? challenge?.challenge_id : undefined,
          code: verification === "email" ? code : undefined,
        },
        { signal: controller.signal },
      );
      setPassword("");
      setCurrentPassword("");
      setConfirmation("");
      setCode("");
      router.replace("/login");
      router.refresh();
    } catch (failure) {
      if (!controller.signal.aborted)
        setError(authErrorMessage(failure, "账户设置保存失败，请重试。"));
    } finally {
      if (operation.current === controller) {
        operation.current = null;
        setBusy(null);
      }
    }
  }

  const wait = Math.max(0, Math.ceil((resendAt - now) / 1000));
  const expired = !!challenge && now >= Date.parse(challenge.expires_at);
  return (
    <section
      aria-labelledby="account-title"
      className="w-full max-w-xl space-y-8"
    >
      <header className="space-y-3">
        <h1 id="account-title" className="text-3xl font-medium tracking-tight">
          账户设置
        </h1>
        <p className="text-muted-foreground text-sm leading-6">
          设置用户名与密码，保存后重新登录。GitHub 与邮箱登录继续关联当前账户。
        </p>
        {session.user.email && (
          <p className="text-muted-foreground text-sm break-all">
            已验证邮箱：{session.user.email}
          </p>
        )}
      </header>
      <form onSubmit={submit} aria-label="设置登录凭据">
        <FieldGroup>
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
          <Tabs
            value={verification}
            onValueChange={(value) => {
              setVerification(value);
              setError("");
            }}
          >
            {session.user.email && (
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
                  maxLength={128}
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  disabled={!!busy}
                />
                <FieldDescription>
                  已有密码时填写；首次为 GitHub 或邮箱账户设置密码时可以留空。
                </FieldDescription>
              </Field>
            </TabsContent>
            {session.user.email && (
              <TabsContent value="email">
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
                    className="self-start"
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
              </TabsContent>
            )}
          </Tabs>
          <FieldDescription>
            保存会撤销当前账户的所有已有会话，请在完成后重新登录。
          </FieldDescription>
          {error && (
            <p role="alert" className="text-destructive text-sm leading-6">
              {error}
            </p>
          )}
          <Button type="submit" className="self-start" disabled={!!busy}>
            {busy === "save" ? "正在保存…" : "保存并重新登录"}
          </Button>
          {busy && (
            <Button
              type="button"
              variant="ghost"
              className="self-start"
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

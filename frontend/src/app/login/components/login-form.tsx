"use client";
import * as UI from "@/components/ui/content";

import { Alert, AlertDescription } from "@/components/ui/alert";

import { useRouter } from "next/navigation";
import { EyeIcon, EyeOffIcon } from "lucide-react";
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
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group";
import { LoginFormLayout, LoginFormSkeleton } from "./login-form-layout";
import { ApiRequestError } from "@/request";

type LoginMethod = "password" | "email" | "github";
type LoginField = "username" | "password" | "email" | "code";

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
  const [invalidFields, setInvalidFields] = useState<
    Partial<Record<LoginField, boolean>>
  >({});
  const feedbackId = useId();
  const oauthNoticeShown = useRef(false);
  const operation = useRef<AbortController | null>(null);
  const credentialInput = useRef<HTMLInputElement | null>(null);
  const passwordInput = useRef<HTMLInputElement | null>(null);
  const codeInput = useRef<HTMLInputElement | null>(null);
  const correctionField = useRef<LoginField | null>(null);
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

  useEffect(() => {
    if (busy || !correctionField.current) return;
    const field = correctionField.current;
    correctionField.current = null;
    const input =
      field === "password"
        ? passwordInput.current
        : field === "code"
          ? codeInput.current
          : credentialInput.current;
    input?.focus();
  }, [busy, invalidFields]);

  function clearFieldError(field: LoginField) {
    setInvalidFields((current) => ({ ...current, [field]: false }));
  }

  function markInvalidFields(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const inputs = Array.from(event.currentTarget.elements).filter(
      (element): element is HTMLInputElement =>
        element instanceof HTMLInputElement && !element.validity.valid,
    );
    setInvalidFields(
      Object.fromEntries(inputs.map((input) => [input.name, true])),
    );
    const first = inputs[0];
    first?.focus();
    toast.error(first?.validationMessage || "请检查输入内容。", {
      id: feedbackId,
    });
  }

  function markRequestFields(failure: unknown, kind: NonNullable<typeof busy>) {
    if (!(failure instanceof ApiRequestError) || failure.kind !== "http")
      return;
    let fields: LoginField[] = [];
    if (failure.status === 422) {
      fields = (failure.details ?? []).flatMap((detail) => {
        const field = detail.location.at(-1);
        return field === "username" ||
          field === "password" ||
          field === "email" ||
          field === "code"
          ? [field]
          : [];
      });
    } else if (failure.status === 401) {
      if (
        kind === "password" &&
        (!failure.code || failure.code === "invalid_credentials")
      )
        fields = ["username", "password"];
      if (
        kind === "email" &&
        (!failure.code || failure.code === "invalid_email_code")
      )
        fields = ["code"];
    }
    if (!fields.length) return;
    setInvalidFields(Object.fromEntries(fields.map((field) => [field, true])));
    correctionField.current = fields[0];
  }

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
    setInvalidFields({});
    toast.dismiss(feedbackId);
    try {
      await action(controller.signal);
    } catch (failure) {
      if (!controller.signal.aborted) {
        markRequestFields(failure, kind);
        toast.error(authErrorMessage(failure, "登录未完成，请重试。"), {
          id: feedbackId,
        });
      }
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
    setInvalidFields({});
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
          <ToggleGroup
            // Keep pressed-button semantics; the controlled value allows one method.
            type="multiple"
            variant="outline"
            size="lg"
            aria-label="登录方式"
            className="mb-5 w-full"
            value={method === "github" ? [] : [method]}
            disabled={!ready}
            onValueChange={(values) => {
              const next = values.at(-1);
              if (
                ready &&
                (next === "password" || next === "email") &&
                next !== method &&
                options[next]
              )
                changeMethod(next);
            }}
          >
            <ToggleGroupItem
              value="password"
              aria-label="使用账号密码登录"
              className="min-w-0 flex-1"
              disabled={!ready || !options.password}
            >
              账号密码
            </ToggleGroupItem>
            <ToggleGroupItem
              value="email"
              aria-label="使用邮箱验证码登录"
              className="min-w-0 flex-1"
              disabled={!ready || !options.email}
            >
              邮箱验证码
            </ToggleGroupItem>
          </ToggleGroup>
          {(!options.password || !options.email) && (
            <UI.Content className="mb-5 flex flex-col gap-2">
              {!options.password && (
                <UI.Text tone="muted" size="xs">
                  账号密码登录暂未启用。
                </UI.Text>
              )}
              {!options.email && (
                <UI.Text tone="muted" size="xs">
                  邮箱验证码登录尚未配置。
                </UI.Text>
              )}
            </UI.Content>
          )}
          {method === "password" && options.password && (
            <UI.Form
              onSubmit={submitPassword}
              onInvalidCapture={markInvalidFields}
              aria-label="账号密码登录"
            >
              <FieldGroup>
                <Field
                  data-disabled={!ready}
                  data-invalid={invalidFields.username}
                >
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
                    aria-invalid={!!invalidFields.username}
                    value={username}
                    onChange={(event) => {
                      setUsername(event.target.value);
                      clearFieldError("username");
                    }}
                    disabled={!ready}
                  />
                </Field>
                <Field data-invalid={invalidFields.password}>
                  <FieldLabel htmlFor="login-password">密码</FieldLabel>
                  <InputGroup>
                    <InputGroupInput
                      ref={passwordInput}
                      id="login-password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="current-password"
                      required
                      maxLength={128}
                      placeholder="输入密码"
                      aria-invalid={!!invalidFields.password}
                      value={password}
                      onChange={(event) => {
                        setPassword(event.target.value);
                        clearFieldError("password");
                      }}
                      disabled={!ready}
                    />
                    <InputGroupAddon align="inline-end">
                      <InputGroupButton
                        aria-label={showPassword ? "隐藏密码" : "显示密码"}
                        aria-pressed={showPassword}
                        aria-controls="login-password"
                        size="icon-sm"
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
                  className="w-full"
                  aria-busy={busy === "password"}
                  disabled={!ready}
                >
                  {busy === "password" ? "正在登录…" : "登录并进入工作区"}
                </Button>
              </FieldGroup>
            </UI.Form>
          )}
          {method === "email" && options.email && (
            <UI.Form
              onSubmit={submitEmail}
              onInvalidCapture={markInvalidFields}
              aria-label="邮箱验证码登录"
            >
              <FieldGroup>
                <Field
                  data-disabled={!ready}
                  data-invalid={invalidFields.email}
                >
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
                    aria-invalid={!!invalidFields.email}
                    value={email}
                    onChange={(event) => {
                      setEmail(event.target.value);
                      setChallenge(null);
                      setCode("");
                      clearFieldError("email");
                      clearFieldError("code");
                      toast.dismiss(feedbackId);
                    }}
                    disabled={!ready}
                  />
                  <FieldDescription>
                    首次使用此邮箱？验证后设置密码，即可使用邮箱和密码登录。
                  </FieldDescription>
                </Field>
                {challenge && (
                  <Field
                    data-disabled={!ready || expired}
                    data-invalid={invalidFields.code}
                  >
                    <FieldLabel htmlFor="login-code">验证码</FieldLabel>
                    <Input
                      ref={codeInput}
                      id="login-code"
                      name="code"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      pattern="[0-9]{6}"
                      required
                      minLength={6}
                      maxLength={6}
                      placeholder="输入 6 位验证码"
                      aria-invalid={!!invalidFields.code}
                      value={code}
                      onChange={(event) => {
                        setCode(event.target.value);
                        clearFieldError("code");
                      }}
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
                  className="w-full"
                  aria-busy={busy === "email-code" || busy === "email"}
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
                    size="lg"
                    disabled={!ready || wait > 0}
                    onClick={sendCode}
                  >
                    {wait ? `${wait} 秒后可重新发送` : "重新发送验证码"}
                  </Button>
                )}
              </FieldGroup>
            </UI.Form>
          )}
          {method === "github" && (
            <Alert role="status">
              <AlertDescription>请选择下方可用的登录方式。</AlertDescription>
            </Alert>
          )}
          <UI.Content
            className="mt-5 flex flex-col gap-4"
            role="group"
            aria-label="其他登录方式"
          >
            <UI.Content className="flex items-center gap-3">
              <Separator className="flex-1" />
              <UI.Text as="span" tone="muted" size="xs">
                或使用其他方式
              </UI.Text>
              <Separator className="flex-1" />
            </UI.Content>
            <Button
              type="button"
              variant="outline"
              size="lg"
              className="w-full gap-3"
              aria-busy={busy === "github"}
              disabled={!ready || !options.github}
              onClick={githubLogin}
            >
              {busy === "github" ? "正在前往 GitHub…" : "使用 GitHub 登录"}
            </Button>
            {!options.github && (
              <UI.Text tone="muted" size="xs">
                GitHub 登录尚未配置。
              </UI.Text>
            )}
          </UI.Content>
        </>
      )}
    </LoginFormLayout>
  );
}

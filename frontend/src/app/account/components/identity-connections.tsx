"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";

import {
  getLoginOptions,
  linkIdentityEmail,
  sendEmailLinkCode,
  startGithubLink,
} from "@/api/identity";
import { authErrorMessage } from "@/components/auth/auth-error";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";

export function IdentityConnections({
  session,
  oauthError,
  githubLinked = false,
}: {
  session: HotKeyAPI.IdentitySessionView;
  oauthError?: string;
  githubLinked?: boolean;
}) {
  const router = useRouter();
  const [options, setOptions] = useState<HotKeyAPI.LoginOptionsView | null>(
    null,
  );
  const [account, setAccount] = useState(session.user);
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] =
    useState<HotKeyAPI.EmailChallengeView | null>(null);
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(0);
  const [busy, setBusy] = useState<"email" | "send" | "github" | null>(null);
  const operation = useRef<AbortController | null>(null);
  const noticeShown = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    getLoginOptions({ signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) setOptions(value);
      })
      .catch((failure) => {
        if (!controller.signal.aborted)
          toast.error(
            authErrorMessage(failure, "登录方式读取失败，请刷新重试。"),
          );
      });
    return () => {
      controller.abort();
      operation.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (noticeShown.current || (!oauthError && !githubLinked)) return;
    noticeShown.current = true;
    if (oauthError)
      toast.error(
        oauthError === "identity_link_conflict"
          ? "此 GitHub 身份已绑定其他账户，无法连接。"
          : "GitHub 连接未完成，请重新授权。",
      );
    else toast.success("GitHub 已连接，可用于登录当前账户。");
    // Remove the one-time callback result so refreshing does not repeat feedback.
    router.replace("/account", { scroll: false });
  }, [oauthError, githubLinked, router]);
  useEffect(() => {
    if (!resendAt) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [resendAt]);

  async function sendCode(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy("send");
    try {
      const value = await sendEmailLinkCode(
        { email },
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      const sentAt = Date.now();
      setChallenge(value);
      setCode("");
      setNow(sentAt);
      setResendAt(sentAt + value.resend_after_seconds * 1000);
      toast.success("验证码已发送，请检查邮箱。");
    } catch (failure) {
      if (!controller.signal.aborted)
        toast.error(authErrorMessage(failure, "验证码发送失败，请重试。"));
    } finally {
      if (operation.current === controller) {
        operation.current = null;
        setBusy(null);
      }
    }
  }
  async function bindEmail() {
    if (busy || !challenge) return;
    if (!/^[0-9]{6}$/.test(code) || now >= Date.parse(challenge.expires_at)) {
      toast.error("请填写有效的六位邮箱验证码。");
      return;
    }
    const controller = new AbortController();
    operation.current = controller;
    setBusy("email");
    try {
      const updated = await linkIdentityEmail(
        { challenge_id: challenge.challenge_id, code },
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setAccount(updated.user);
      setOpen(false);
      setChallenge(null);
      setCode("");
      toast.success("邮箱已绑定，可用于登录当前账户。其他设备的旧会话已退出。");
      router.refresh();
    } catch (failure) {
      if (!controller.signal.aborted)
        toast.error(authErrorMessage(failure, "邮箱绑定失败，请重试。"));
    } finally {
      if (operation.current === controller) {
        operation.current = null;
        setBusy(null);
      }
    }
  }
  async function connectGithub() {
    if (busy) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy("github");
    try {
      const value = await startGithubLink({ signal: controller.signal });
      if (!controller.signal.aborted)
        window.location.assign(value.authorization_url);
    } catch (failure) {
      if (!controller.signal.aborted)
        toast.error(authErrorMessage(failure, "GitHub 连接失败，请重试。"));
    } finally {
      if (operation.current === controller) {
        operation.current = null;
        setBusy(null);
      }
    }
  }
  const wait = Math.max(0, Math.ceil((resendAt - now) / 1000));
  return (
    <section
      aria-labelledby="connections-title"
      className="flex w-full max-w-xl flex-col gap-6"
    >
      <header className="flex flex-col gap-2">
        <h2 id="connections-title" className="text-xl font-medium">
          登录方式
        </h2>
        <p className="text-muted-foreground text-sm">
          邮箱和 GitHub 共用当前账户及工作区。
        </p>
      </header>
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="font-medium">邮箱</p>
          <p className="text-muted-foreground text-sm break-all">
            {account.email ?? "尚未绑定"}
          </p>
        </div>
        <Dialog
          open={open}
          onOpenChange={(value) => {
            setOpen(value);
            if (!value) {
              operation.current?.abort();
              operation.current = null;
              setBusy(null);
              setChallenge(null);
              setCode("");
            }
          }}
        >
          <DialogTrigger asChild>
            <Button variant="outline" disabled={!options?.email || !!busy}>
              {account.email ? "更换邮箱" : "绑定邮箱"}
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>
                {account.email ? "更换登录邮箱" : "绑定登录邮箱"}
              </DialogTitle>
              <DialogDescription>
                验证新邮箱后即可用于登录当前账户。
              </DialogDescription>
            </DialogHeader>
            <form
              onSubmit={(event) => {
                if (challenge) {
                  event.preventDefault();
                  void bindEmail();
                } else void sendCode(event);
              }}
              aria-label="绑定登录邮箱"
            >
              <FieldGroup>
                <Field data-disabled={!!busy}>
                  <FieldLabel htmlFor="link-email">新邮箱</FieldLabel>
                  <Input
                    id="link-email"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    disabled={!!busy}
                    onChange={(event) => {
                      setEmail(event.target.value);
                      setChallenge(null);
                      setCode("");
                    }}
                  />
                </Field>
                <Button
                  type={challenge ? "button" : "submit"}
                  variant="outline"
                  disabled={!!busy || wait > 0}
                  onClick={
                    challenge ? (event) => void sendCode(event) : undefined
                  }
                >
                  {busy === "send"
                    ? "正在发送…"
                    : wait
                      ? `${wait} 秒后可重新发送`
                      : "发送验证码"}
                </Button>
                {challenge && (
                  <>
                    <Field data-disabled={!!busy}>
                      <FieldLabel htmlFor="link-code">邮箱验证码</FieldLabel>
                      <Input
                        id="link-code"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        pattern="[0-9]{6}"
                        maxLength={6}
                        value={code}
                        disabled={!!busy}
                        onChange={(event) => setCode(event.target.value)}
                      />
                    </Field>
                    <Button type="submit" disabled={!!busy}>
                      {busy === "email" ? "正在绑定…" : "验证并绑定"}
                    </Button>
                  </>
                )}
              </FieldGroup>
            </form>
          </DialogContent>
        </Dialog>
      </div>
      {!options?.email && options && (
        <p className="text-muted-foreground text-sm">邮箱登录暂不可用。</p>
      )}
      <Separator />
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="font-medium">GitHub</p>
          <p className="text-muted-foreground text-sm">
            {account.github_connected ? "已连接" : "尚未连接"}
          </p>
        </div>
        {!account.github_connected && (
          <Button
            variant="outline"
            disabled={!options?.github || !!busy}
            onClick={() => void connectGithub()}
          >
            {busy === "github" ? "正在跳转…" : "连接 GitHub"}
          </Button>
        )}
      </div>
      {!options?.github && options && (
        <p className="text-muted-foreground text-sm">GitHub 登录暂不可用。</p>
      )}
    </section>
  );
}

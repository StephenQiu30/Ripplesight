"use client";
import * as UI from "@/components/ui/content";

import { toast } from "sonner";

import { useEffect, useRef, useState } from "react";

import { updateSourceConnection } from "@/api/laiyuannengli";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ApiRequestError } from "@/request";

export function SourceConnectionActions({
  platform,
  onChanged,
}: {
  platform: HotKeyAPI.SourcePlatformView;
  onChanged: () => Promise<void>;
}) {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const submitting = useRef(false);
  const confirmOrigin = useRef<HTMLButtonElement | null>(null);
  const enableButton = useRef<HTMLButtonElement | null>(null);
  const disableButton = useRef<HTMLButtonElement | null>(null);
  const [pending, setPending] = useState(false);
  const [confirm, setConfirm] =
    useState<HotKeyAPI.SourceConnectionStatus | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [hostsText, setHostsText] = useState(platform.allowed_hosts.join("\n"));
  const editableHosts = platform.source_key === "web";
  const hosts = Array.from(
    new Set(
      hostsText
        .split(/\s+/)
        .map((host) => host.trim().toLowerCase())
        .filter(Boolean),
    ),
  );
  const hostsInvalid = hosts.length > 32;
  const hostsChanged = hosts.join("\n") !== platform.allowed_hosts.join("\n");
  const active = platform.connection_status === "active";
  const canEnable = editableHosts
    ? hosts.length > 0 && !hostsInvalid
    : platform.credential_configured || platform.allowed_hosts.length > 0;
  const usesPublicConnection =
    !platform.has_credentials && platform.allowed_hosts.length > 0;
  const safetyPaused =
    platform.source_key === "bilibili" && platform.safety_stop_reason != null;
  const safetyMessage =
    platform.safety_stop_reason === "rate_limited"
      ? "B 站访问频繁，来源已暂停。请本人检查访问频率和账号状态后再恢复。"
      : "B 站登录态或验证要求发生变化，来源已暂停。请本人检查账号和验证状态后再恢复。";
  const label =
    editableHosts && active
      ? "保存域名"
      : platform.connection_version === null
        ? "配置连接"
        : platform.credential_update_available
          ? "替换连接"
          : active
            ? "已配置"
            : "重新启用";

  async function save(status: HotKeyAPI.SourceConnectionStatus) {
    if (
      submitting.current ||
      (status === "active" && (!canEnable || (safetyPaused && !reviewed)))
    )
      return;
    submitting.current = true;
    setPending(true);
    try {
      await updateSourceConnection(
        { source_key: platform.source_key },
        {
          expected_version: platform.connection_version ?? 0,
          status,
          owner_confirmed: safetyPaused && reviewed,
          ...(editableHosts && status === "active"
            ? { allowed_hosts: hosts }
            : {}),
        },
      );
      if (!mounted.current) return;
      toast.success(
        status === "disabled"
          ? "连接已停用，历史资料仍可读取。"
          : "连接已保存，能力仍需重新验证。",
      );
      await onChanged();
      if (!mounted.current) return;
      setConfirm(null);
      setReviewed(false);
    } catch (failure) {
      if (!mounted.current) return;
      if (failure instanceof ApiRequestError && failure.kind === "cancelled")
        return;
      setConfirm(null);
      setReviewed(false);
      toast.error(
        failure instanceof ApiRequestError
          ? `${failure.message}${failure.requestId ? ` 请求编号：${failure.requestId}` : ""}`
          : "连接更新失败，请刷新状态后重试。",
        { action: { label: "刷新状态", onClick: () => void onChanged() } },
      );
    } finally {
      submitting.current = false;
      if (mounted.current) setPending(false);
    }
  }

  return (
    <UI.Content
      role="group"
      className="flex max-w-md flex-col gap-3"
      aria-label={`${platform.display_name}连接管理`}
    >
      {editableHosts ? (
        <FieldGroup>
          <Field data-invalid={hostsInvalid} data-disabled={pending}>
            <FieldLabel htmlFor="source-allowed-hosts">
              允许访问的域名
            </FieldLabel>
            <Textarea
              id="source-allowed-hosts"
              value={hostsText}
              onChange={(event) => {
                const next = event.target.value;
                setHostsText(next);
                if (
                  new Set(next.split(/\s+/).filter(Boolean)).size > 32 &&
                  !hostsInvalid
                )
                  toast.error("最多允许 32 个域名。");
              }}
              disabled={pending}
              aria-invalid={hostsInvalid}
              aria-describedby="source-hosts-description"
              placeholder="example.com"
            />
            <FieldDescription id="source-hosts-description">
              每行一个精确域名，最多 32
              个，不包含协议、路径或通配符。保存后仍需由维护者配置准入政策并完成验证。
            </FieldDescription>
          </Field>
        </FieldGroup>
      ) : null}
      <UI.Content className="flex flex-wrap gap-2">
        <Button
          ref={enableButton}
          variant="outline"
          disabled={
            pending ||
            !canEnable ||
            (active &&
              !platform.credential_update_available &&
              !(editableHosts && hostsChanged))
          }
          onClick={(event) => {
            confirmOrigin.current = event.currentTarget;
            setConfirm("active");
          }}
        >
          {pending ? "正在保存…" : label}
        </Button>
        {active ? (
          <Button
            ref={disableButton}
            variant="ghost"
            disabled={pending}
            onClick={(event) => {
              confirmOrigin.current = event.currentTarget;
              setConfirm("disabled");
            }}
          >
            停用连接
          </Button>
        ) : null}
      </UI.Content>
      {safetyPaused ? (
        <Alert>
          <AlertTitle>来源已暂停</AlertTitle>
          <AlertDescription>{safetyMessage}</AlertDescription>
        </Alert>
      ) : null}
      {!canEnable && !editableHosts ? (
        <UI.Text className="text-muted-foreground text-sm">
          {platform.source_key === "bilibili" ||
          platform.status === "unconfigured"
            ? "尚未完成来源配置。请维护者配置对应来源预设；需要凭据的来源，请维护者先配置服务端凭据。"
            : "请维护者先配置服务端凭据。"}
          页面不接收或显示会话秘密。
        </UI.Text>
      ) : null}
      <AlertDialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!open && !pending) {
            setConfirm(null);
            setReviewed(false);
          }
        }}
      >
        <AlertDialogContent
          className="max-h-svh overflow-y-auto"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const target = [
              confirmOrigin.current,
              enableButton.current,
              disableButton.current,
            ].find((button) => button?.isConnected && !button.disabled);
            target?.focus();
          }}
          onEscapeKeyDown={(event) => {
            if (pending) event.preventDefault();
          }}
        >
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirm === "disabled"
                ? "停用"
                : platform.connection_version === null
                  ? "配置"
                  : platform.credential_update_available
                    ? "替换"
                    : "重新启用"}
              {platform.display_name}连接？
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === "disabled"
                ? "停止接受该连接的新任务。历史资料保留，不删除已有结果。"
                : safetyPaused
                  ? "请本人核查账号和访问状态。确认后仅恢复连接执行权，新版本仍需低频验证，不会自动发起平台请求。"
                  : editableHosts
                    ? "保存这些精确域名作为公开网页连接的访问范围。连接的新版本仍需准入政策与实际读取验证，确认后不会自动发起采集请求。"
                    : usesPublicConnection
                      ? "沿用当前来源配置。连接的新版本仍需重新验证，确认后不会自动发起采集请求。"
                      : "使用维护者已配置的服务端凭据。连接的新版本仍需重新验证，确认后不会自动发起采集请求。"}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {safetyPaused && confirm === "active" ? (
            <FieldGroup>
              <Field orientation="horizontal" data-disabled={pending}>
                <Checkbox
                  id="owner-reviewed-bilibili"
                  name="owner_reviewed_bilibili"
                  checked={reviewed}
                  disabled={pending}
                  onCheckedChange={(checked) => setReviewed(checked === true)}
                />
                <FieldContent>
                  <FieldLabel htmlFor="owner-reviewed-bilibili">
                    我已本人核查 B 站账号与访问状态，并决定人工恢复。
                  </FieldLabel>
                </FieldContent>
              </Field>
            </FieldGroup>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={pending}>取消</AlertDialogCancel>
            <Button
              disabled={
                pending ||
                (confirm === "active" &&
                  (!canEnable || (safetyPaused && !reviewed)))
              }
              onClick={() => {
                if (confirm) void save(confirm);
              }}
            >
              {pending ? "正在保存…" : "确认"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </UI.Content>
  );
}

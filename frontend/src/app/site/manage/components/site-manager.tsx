"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import {
  getOperatorSiteConfiguration,
  saveOperatorSiteConfiguration,
} from "@/api/zhandiziliao";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError } from "@/request";

export function SiteManager() {
  const [token, setToken] = useState("");
  const [view, setView] = useState<HotKeyAPI.SiteConfigurationView | null>(
    null,
  );
  const [enabled, setEnabled] = useState(false);
  const [title, setTitle] = useState("联系");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [reason, setReason] = useState("");
  const [qrAction, setQrAction] = useState<"keep" | "replace" | "clear">(
    "keep",
  );
  const [image, setImage] = useState<HotKeyAPI.ContactImageInput | null>(null);
  const [feishuAction, setFeishuAction] = useState<
    "keep" | "replace" | "clear"
  >("keep");
  const [feishuImage, setFeishuImage] =
    useState<HotKeyAPI.ContactImageInput | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const operations = useRef(new Map<string, string>());
  const contextRevision = useRef(0);
  useEffect(
    () => () => {
      contextRevision.current += 1;
    },
    [],
  );
  const headers = { "X-HotKey-Operator-Token": token };
  function apply(value: HotKeyAPI.SiteConfigurationView) {
    setView(value);
    setEnabled(value.contact_enabled);
    setTitle(value.contact_title);
    setText(value.contact_text);
    setUrl(value.contact_url ?? "");
    setQrAction("keep");
    setImage(null);
    setFeishuAction("keep");
    setFeishuImage(null);
  }
  function fail(failure: unknown) {
    setError(
      failure instanceof ApiRequestError && failure.status === 409
        ? "配置已被修改或操作冲突，请重新读取后保存。"
        : failure instanceof ApiRequestError &&
            (failure.status === 401 || failure.status === 403)
          ? "运营令牌无效或入口未启用。"
          : "操作失败，请保留输入后重试。",
    );
  }
  async function load() {
    if (!token) return;
    setBusy(true);
    setError("");
    setNotice("");
    const revision = contextRevision.current;
    try {
      const value = await getOperatorSiteConfiguration({ headers });
      if (revision === contextRevision.current) apply(value);
    } catch (failure) {
      if (revision === contextRevision.current) fail(failure);
    } finally {
      if (revision === contextRevision.current) setBusy(false);
    }
  }
  async function choose(file: File | undefined, channel: "wechat" | "feishu") {
    if (!file) return;
    if (
      file.size > 2 * 1024 * 1024 ||
      !["image/png", "image/jpeg", "image/webp", "image/gif"].includes(
        file.type,
      )
    ) {
      setError("图片需为 PNG/JPEG/WebP/GIF，最多 2 MiB。");
      return;
    }
    try {
      const encoded = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () =>
          typeof reader.result === "string"
            ? resolve(reader.result.split(",")[1])
            : reject(new Error("file"));
        reader.onerror = () => reject(new Error("file"));
        reader.readAsDataURL(file);
      });
      const value: HotKeyAPI.ContactImageInput = {
        mime: file.type as HotKeyAPI.ContactImageInput["mime"],
        data_base64: encoded,
      };
      if (channel === "wechat") {
        setImage(value);
        setQrAction("replace");
      } else {
        setFeishuImage(value);
        setFeishuAction("replace");
      }
      setError("");
    } catch {
      setError("无法读取图片，请重新选择。");
    }
  }
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!view || !reason.trim() || !token) return;
    const body = {
      expected_revision: view.revision,
      reason: reason.trim(),
      contact_enabled: enabled,
      contact_title: title.trim(),
      contact_text: text,
      contact_url: url.trim() || null,
      wechat_qr_action: qrAction,
      wechat_image: qrAction === "replace" ? image : null,
      feishu_qr_action: feishuAction,
      feishu_image: feishuAction === "replace" ? feishuImage : null,
    };
    const key = JSON.stringify(body);
    if (!operations.current.has(key))
      operations.current.set(key, crypto.randomUUID());
    setBusy(true);
    setError("");
    setNotice("");
    const revision = contextRevision.current;
    try {
      const value = await saveOperatorSiteConfiguration(
        { ...body, operation_id: operations.current.get(key)! },
        { headers },
      );
      if (revision === contextRevision.current) {
        apply(value);
        setNotice("已保存。公开联系页按当前启用状态读取。");
      }
    } catch (failure) {
      if (revision === contextRevision.current) fail(failure);
    } finally {
      if (revision === contextRevision.current) setBusy(false);
    }
  }
  return (
    <>
      <div>
        <h1 className="text-3xl font-medium">站点联系设置</h1>
        <p className="text-muted-foreground mt-4 text-sm leading-7">
          运营令牌仅保存在当前页面内存。启用、更换和关闭均保存修订与原因；关闭后旧二维码链接不可读取。
        </p>
        <div className="mt-8 space-y-3">
          <Label htmlFor="site-token">运营令牌</Label>
          <Input
            id="site-token"
            type="password"
            autoComplete="off"
            value={token}
            onChange={(event) => {
              contextRevision.current += 1;
              setToken(event.target.value);
              setView(null);
              setBusy(false);
              setError("");
              setNotice("");
              operations.current.clear();
            }}
          />
          <Button variant="outline" onClick={load} disabled={busy || !token}>
            读取配置
          </Button>
        </div>
        {error && (
          <p role="alert" className="text-destructive mt-5">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="mt-5">
            {notice}
          </p>
        )}
        {view && (
          <form className="mt-8 space-y-6" onSubmit={save}>
            <p className="text-muted-foreground text-sm">
              当前修订 {view.revision}
            </p>
            <Label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
              />
              启用公开联系资料
            </Label>
            <div className="space-y-2">
              <Label htmlFor="contact-title">标题</Label>
              <Input
                id="contact-title"
                required
                maxLength={100}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="contact-text">联系说明</Label>
              <Textarea
                id="contact-text"
                maxLength={4000}
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="contact-url">HTTP(S) 联系入口</Label>
              <Input
                id="contact-url"
                type="url"
                value={url}
                maxLength={1000}
                onChange={(event) => setUrl(event.target.value)}
              />
            </div>
            <div className="space-y-3">
              <Label htmlFor="contact-image">微信二维码（最多 2 MiB）</Label>
              <Input
                id="contact-image"
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                onChange={(event) =>
                  void choose(event.target.files?.[0], "wechat")
                }
              />
              <p className="text-muted-foreground text-sm">
                {qrAction === "replace"
                  ? "保存时替换为已选图片"
                  : qrAction === "clear"
                    ? "保存时删除当前图片"
                    : view.wechat_qr_url
                      ? "保留现有图片"
                      : "尚无图片"}
              </p>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setQrAction("clear");
                  setImage(null);
                }}
              >
                移除微信图片
              </Button>
            </div>
            <div className="space-y-3">
              <Label htmlFor="feishu-image">飞书二维码（最多 2 MiB）</Label>
              <Input
                id="feishu-image"
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                onChange={(event) =>
                  void choose(event.target.files?.[0], "feishu")
                }
              />
              <p className="text-muted-foreground text-sm">
                {feishuAction === "replace"
                  ? "保存时替换为已选飞书图片"
                  : feishuAction === "clear"
                    ? "保存时删除当前飞书图片"
                    : view.feishu_qr_url
                      ? "保留现有飞书图片"
                      : "尚无飞书图片"}
              </p>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setFeishuAction("clear");
                  setFeishuImage(null);
                }}
              >
                移除飞书图片
              </Button>
            </div>
            <div className="space-y-2">
              <Label htmlFor="site-reason">修改原因</Label>
              <Textarea
                id="site-reason"
                required
                maxLength={2000}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </div>
            <Button
              type="submit"
              disabled={
                busy ||
                !reason.trim() ||
                (qrAction === "replace" && !image) ||
                (feishuAction === "replace" && !feishuImage)
              }
            >
              保存配置
            </Button>
          </form>
        )}
        <p className="mt-10 text-sm">
          <Link href="/contact" className="underline">
            查看公开联系页
          </Link>
        </p>
      </div>
    </>
  );
}

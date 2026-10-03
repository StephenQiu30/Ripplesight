"use client";
import { Alert, AlertDescription } from "@/components/ui/alert";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";

import { getPublicContact } from "@/api/zhandiziliao";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/request";

export function ContactPanel() {
  const [view, setView] = useState<HotKeyAPI.PublicContactView | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    getPublicContact({ signal: controller.signal })
      .then((value) => {
        if (controller.signal.aborted) return;
        setView(value);
        setError("");
      })
      .catch((failure) => {
        if (controller.signal.aborted) return;
        if (failure instanceof ApiRequestError && failure.kind === "cancelled")
          return;
        setView(null);
        setError("联系资料读取失败，请重新读取。");
      });
    return () => controller.abort();
  }, [refresh]);
  return (
    <section aria-label="联系资料" className="flex flex-col gap-y-6">
      {error ? (
        <Alert>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : !view ? (
        <p role="status">正在读取…</p>
      ) : view.enabled ? (
        <>
          <h2 className="text-foreground text-lg font-medium">{view.title}</h2>
          <p className="whitespace-pre-wrap">{view.text}</p>
          {view.url && (
            <a
              href={view.url}
              target="_blank"
              rel="noopener noreferrer"
              className="underline"
            >
              打开联系入口
            </a>
          )}
          {[
            { url: view.wechat_qr_url, label: "微信二维码" },
            { url: view.feishu_qr_url, label: "飞书二维码" },
          ].map(
            ({ url, label }) =>
              url && (
                <figure key={label} className="flex flex-col gap-y-2">
                  <figcaption className="text-sm">{label}</figcaption>
                  <Image
                    src={url}
                    alt={label}
                    width={320}
                    height={320}
                    unoptimized
                    className="h-auto max-w-full"
                  />
                </figure>
              ),
          )}
        </>
      ) : (
        <p>维护者尚未启用公开联系资料。登录后可以提交站内反馈。</p>
      )}
      <div className="flex flex-wrap gap-5">
        <Button
          variant="outline"
          onClick={() => setRefresh((value) => value + 1)}
        >
          重新读取
        </Button>
        <Button variant="ghost" asChild>
          <Link href="/feedback">登录后提交反馈</Link>
        </Button>
      </div>
    </section>
  );
}

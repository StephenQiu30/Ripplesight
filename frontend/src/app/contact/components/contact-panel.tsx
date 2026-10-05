"use client";
import * as UI from "@/components/ui/content";

import { Spinner } from "@/components/ui/spinner";
import { Item, ItemContent, ItemDescription } from "@/components/ui/item";
import { Alert, AlertDescription } from "@/components/ui/alert";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { getPublicContact } from "@/api/zhandiziliao";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/request";

export function ContactPanel() {
  const [view, setView] = useState<HotKeyAPI.PublicContactView | null>(null);
  const [failed, setFailed] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    getPublicContact({ signal: controller.signal })
      .then((value) => {
        if (controller.signal.aborted) return;
        setView(value);
        setFailed(false);
      })
      .catch((failure) => {
        if (controller.signal.aborted) return;
        if (failure instanceof ApiRequestError && failure.kind === "cancelled")
          return;
        setView(null);
        setFailed(true);
        toast.error("联系资料读取失败，请重新读取。");
      });
    return () => controller.abort();
  }, [refresh]);
  return (
    <UI.Content
      as="section"
      aria-label="联系资料"
      className="flex flex-col gap-y-6"
    >
      {failed ? (
        <Alert>
          <AlertDescription>联系资料暂不可用，可以重新读取。</AlertDescription>
        </Alert>
      ) : !view ? (
        <Item role="status">
          <Spinner aria-hidden="true" />
          <ItemContent>
            <ItemDescription className="line-clamp-none">
              正在读取…
            </ItemDescription>
          </ItemContent>
        </Item>
      ) : view.enabled ? (
        <>
          <UI.Heading level={2} className="text-foreground text-lg font-medium">
            {view.title}
          </UI.Heading>
          <UI.Text className="whitespace-pre-wrap">{view.text}</UI.Text>
          {view.url && (
            <UI.TextLink
              href={view.url}
              target="_blank"
              rel="noopener noreferrer"
              className="underline"
            >
              打开联系入口
            </UI.TextLink>
          )}
          {[
            { url: view.wechat_qr_url, label: "微信二维码" },
            { url: view.feishu_qr_url, label: "飞书二维码" },
          ].map(
            ({ url, label }) =>
              url && (
                <UI.Content
                  as="figure"
                  key={label}
                  className="flex flex-col gap-y-2"
                >
                  <UI.Content as="figcaption" className="text-sm">
                    {label}
                  </UI.Content>
                  <Image
                    src={url}
                    alt={label}
                    width={320}
                    height={320}
                    unoptimized
                    className="h-auto max-w-full"
                  />
                </UI.Content>
              ),
          )}
        </>
      ) : (
        <UI.Text>维护者尚未启用公开联系资料。登录后可以提交站内反馈。</UI.Text>
      )}
      <UI.Content className="flex flex-wrap gap-5">
        <Button
          variant="outline"
          onClick={() => setRefresh((value) => value + 1)}
        >
          重新读取
        </Button>
        <Button variant="ghost" asChild>
          <Link href="/feedback">登录后提交反馈</Link>
        </Button>
      </UI.Content>
    </UI.Content>
  );
}

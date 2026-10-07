"use client";

import Link from "next/link";
import { useState } from "react";

import { connectBilibiliChrome } from "@/api/laiyuannengli";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import * as UI from "@/components/ui/content";
import { ApiRequestError } from "@/request";

type Props = { onConnected: () => Promise<void> };

export function ChromeConnection({ onConnected }: Props) {
  const [pending, setPending] = useState(false);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connect() {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      await connectBilibiliChrome();
      setConnected(true);
      await onConnected();
    } catch (failure) {
      setError(
        failure instanceof ApiRequestError &&
          failure.code === "connection_credentials_missing"
          ? "当前账号尚未绑定本机 Chrome 采集。请先完成本机账号绑定，再启用来源。"
          : failure instanceof ApiRequestError &&
              failure.code === "connection_owner_confirmation_required"
            ? "来源已暂停。请打开 B站连接设置，检查停止原因后确认恢复。"
            : failure instanceof ApiRequestError
              ? failure.message
              : "启用失败，请重试。",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>B站关键词监控</CardTitle>
        <CardDescription>
          复用本机 Chrome 登录，免费获取公开视频与一级评论。仅绑定的账号可启用。
          每小时检查，00:00–08:00 静默；每日最多 60 次平台请求，每轮最多 2
          帖、每帖 20 条根评论。 结果为单页样本，不代表全量覆盖。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <UI.Content className="flex flex-wrap items-center gap-3">
          <Button
            disabled={pending || connected}
            onClick={() => void connect()}
          >
            {pending
              ? "正在启用…"
              : connected
                ? "已启用 Chrome 采集"
                : "启用 Chrome 采集"}
          </Button>
          {connected ? (
            <Button variant="outline" asChild>
              <Link href="/monitors/new">创建监控主题</Link>
            </Button>
          ) : null}
        </UI.Content>
        {connected ? (
          <UI.Text role="status" className="text-muted-foreground text-sm">
            来源预设已保存。创建主题后可立即采集；实际可用状态以任务结果为准。
          </UI.Text>
        ) : null}
        {error ? (
          <Alert variant="destructive">
            <AlertTitle>尚未启用</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}

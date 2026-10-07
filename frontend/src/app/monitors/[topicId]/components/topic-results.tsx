"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { listContentRecords } from "@/api/zuopinziliao";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import * as UI from "@/components/ui/content";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/request";

export function TopicResults({ topicId }: { topicId: string }) {
  const [rows, setRows] = useState<HotKeyAPI.ContentRecordSummaryView[] | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const read = useCallback(
    (signal: AbortSignal) =>
      listContentRecords({ topic_id: topicId, limit: 5 }, { signal })
        .then((result) => {
          if (!signal.aborted) {
            setRows(result.items);
            setError(null);
          }
        })
        .catch((failure: unknown) => {
          if (signal.aborted) return;
          setRows(null);
          setError(
            failure instanceof ApiRequestError &&
              (failure.status === 401 || failure.status === 403)
              ? "请登录有权限的账号查看监控结果。"
              : "监控结果加载失败，请重试。",
          );
        }),
    [topicId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void read(controller.signal);
    const timer = setInterval(() => void read(controller.signal), 30_000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [read, refresh]);

  return (
    <UI.Content
      as="section"
      aria-label="最新监控结果"
      className="flex flex-col gap-4"
    >
      <UI.Content className="flex items-center justify-between gap-3">
        <UI.Heading level={3}>最新监控结果</UI.Heading>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setRefresh((value) => value + 1)}
        >
          刷新结果
        </Button>
      </UI.Content>
      <UI.Text tone="muted" size="sm">
        展示最近 5 条入库资料，每 30
        秒检查一次。打开资料可查看已采集评论、原文与采集时间；未标注结果仅代表关键词发现，尚未完成语义相关性判断。
      </UI.Text>
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>无法读取结果</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : rows === null ? (
        <Skeleton className="h-24 w-full" aria-label="正在加载监控结果" />
      ) : rows.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>还没有采集结果</EmptyTitle>
            <EmptyDescription>
              主题运行后，成功入库的资料会显示在这里。可通过任务页核对采集状态。
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        rows.map((row) => {
          const observation = row.latest_observation;
          const version = observation.content_version;
          return (
            <UI.Content
              key={row.id}
              className="flex flex-col gap-2 border-b py-3 last:border-0"
            >
              <Button
                asChild
                variant="link"
                className="h-auto justify-start px-0 text-left whitespace-normal"
              >
                <Link href={`/content/${row.id}`}>
                  {version?.title ||
                    version?.body?.slice(0, 120) ||
                    "查看资料与评论"}
                </Link>
              </Button>
              <UI.Text tone="muted" size="sm">
                {row.source_name || row.source_key} ·{" "}
                {observation.published_at
                  ? `发布于 ${new Date(observation.published_at).toLocaleString()}`
                  : "发布时间未知"}{" "}
                · 采集于 {new Date(observation.observed_at).toLocaleString()}
              </UI.Text>
            </UI.Content>
          );
        })
      )}
    </UI.Content>
  );
}

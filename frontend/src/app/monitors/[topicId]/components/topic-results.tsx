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
import { Badge } from "@/components/ui/badge";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
import { Separator } from "@/components/ui/separator";
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
          if (
            failure instanceof ApiRequestError &&
            (failure.status === 401 || failure.status === 403)
          )
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
      aria-label="当前监控结果"
      className="flex flex-col gap-4"
    >
      <UI.Content className="flex items-center justify-between gap-3">
        <UI.Heading level={3}>当前监控结果</UI.Heading>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setRefresh((value) => value + 1)}
        >
          刷新结果
        </Button>
      </UI.Content>
      <UI.Text tone="muted" size="sm">
        展示当前页最多 5 条资料，按接口顺序排列，每 30 秒刷新。
        关键词发现不等于语义相关，结果尚需核对；打开资料可读原文与评论。
      </UI.Text>
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>
            {rows ? "结果刷新失败，已显示内容可能过期" : "无法读取结果"}
          </AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {rows === null ? (
        error ? null : (
          <Skeleton className="h-24 w-full" aria-label="正在加载监控结果" />
        )
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
        <ItemGroup>
          {rows.map((row, index) => {
            const observation = row.latest_observation;
            const version = observation.content_version;
            const sourceName = row.source_name || row.source_key;
            return (
              <UI.Content key={row.id}>
                {index > 0 && <Separator />}
                <Item role="listitem" className="px-0 py-5">
                  <ItemContent className="min-w-0 gap-3">
                    <UI.Content className="flex flex-wrap items-center gap-3">
                      <Badge variant="outline">
                        {sourceName === "bilibili" ? "B 站" : sourceName}
                      </Badge>
                      <UI.Text tone="muted" size="xs">
                        {
                          { post: "帖子", comment: "评论", webpage: "网页" }[
                            row.object_type
                          ]
                        }
                      </UI.Text>
                      <UI.Text tone="muted" size="xs">
                        {observation.published_at
                          ? `发布于 ${new Date(observation.published_at).toLocaleString()}`
                          : "发布时间未知"}
                      </UI.Text>
                    </UI.Content>
                    <UI.Heading level={4} className="min-w-0 break-words">
                      <UI.TextLink href={`/content/${row.id}`}>
                        {version?.title ||
                          version?.body?.slice(0, 120) ||
                          "查看资料与评论"}
                      </UI.TextLink>
                    </UI.Heading>
                    <UI.Content className="flex flex-wrap items-center justify-between gap-3">
                      <UI.Text tone="muted" size="xs">
                        采集于{" "}
                        {new Date(observation.observed_at).toLocaleString()}
                      </UI.Text>
                      <Button asChild variant="link" size="sm" className="px-0">
                        <Link href={`/content/${row.id}`}>查看内容与评论</Link>
                      </Button>
                    </UI.Content>
                  </ItemContent>
                </Item>
              </UI.Content>
            );
          })}
        </ItemGroup>
      )}
    </UI.Content>
  );
}

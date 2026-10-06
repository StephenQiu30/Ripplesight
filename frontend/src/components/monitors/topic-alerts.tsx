"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listAlerts } from "@/api/gerentufagaojing";
import { PageState } from "@/components/system/page-state";
import * as UI from "@/components/ui/content";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Item, ItemContent, ItemGroup, ItemTitle } from "@/components/ui/item";
import { ApiRequestError } from "@/request";
import { AlertHistory } from "./alert-history";
import { AlertRuleSummary } from "./alert-rule-summary";
import { alertReasonLabel } from "./alert-presenters";
import { readMonitorFailure, type MonitorFailure } from "./monitor-presenters";

export function TopicAlerts({ topicId }: { topicId: string }) {
  const [rules, setRules] = useState<HotKeyAPI.AlertRuleView[] | null>(null);
  const [error, setError] = useState<MonitorFailure | null>(null);
  const [reload, setReload] = useState(0);
  const [historyId, setHistoryId] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void listAlerts({ signal: controller.signal })
      .then((rows) => {
        if (!controller.signal.aborted) {
          setRules(rows.filter((row) => row.topic_id === topicId));
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (caught instanceof ApiRequestError && caught.kind === "cancelled")
          return;
        if (!controller.signal.aborted)
          setError(readMonitorFailure(caught, "告警规则读取失败，请重试。"));
      });
    return () => controller.abort();
  }, [topicId, reload]);
  return (
    <UI.Content
      as="section"
      aria-label="主题告警"
      className="flex min-w-0 flex-col gap-4"
    >
      <UI.Content className="flex flex-wrap items-center justify-between gap-3">
        <UI.Heading level={3}>告警规则与历史</UI.Heading>
        <Button asChild variant="link">
          <Link href="/alerts">管理告警</Link>
        </Button>
      </UI.Content>
      {error ? (
        <PageState
          headingLevel={2}
          state={error.forbidden ? "forbidden" : rules ? "stale" : "error"}
          eyebrow="主题告警"
          title={error.forbidden ? "无权读取主题告警" : "暂时无法读取告警规则"}
          description="请核对账户权限或重试读取。"
          errorCode={error.code}
          httpStatus={error.httpStatus}
          action={
            error.forbidden ? undefined : (
              <Button
                variant="outline"
                onClick={() => setReload((value) => value + 1)}
              >
                重试告警
              </Button>
            )
          }
        />
      ) : null}
      {!rules && !error && (
        <PageState
          headingLevel={2}
          state="loading"
          eyebrow="主题告警"
          title="正在读取告警规则"
          description="正在读取当前主题的告警。"
        />
      )}
      {!error?.forbidden &&
        rules &&
        (rules.length ? (
          <ItemGroup>
            {rules.map((rule) => (
              <Item key={rule.id} role="listitem" variant="muted">
                <ItemContent className="min-w-0 gap-3">
                  <ItemTitle>
                    {rule.name}
                    <Badge variant="secondary">
                      {rule.enabled ? "已启用" : "已关闭"}
                    </Badge>
                  </ItemTitle>
                  <AlertRuleSummary rule={rule} />
                  {rule.reason && (
                    <UI.Text tone="muted" size="sm">
                      {alertReasonLabel(rule.reason)}
                    </UI.Text>
                  )}
                  <Button
                    variant="outline"
                    className="self-start"
                    aria-expanded={historyId === rule.id}
                    onClick={() =>
                      setHistoryId((value) =>
                        value === rule.id ? null : rule.id,
                      )
                    }
                  >
                    评估历史
                  </Button>
                  {historyId === rule.id && (
                    <AlertHistory key={rule.id} ruleId={rule.id} />
                  )}
                </ItemContent>
              </Item>
            ))}
          </ItemGroup>
        ) : (
          <PageState
            headingLevel={2}
            state="empty"
            eyebrow="主题告警"
            title="这个主题尚无告警规则"
            description="可以在告警页设置阈值、冷却时间与通知目标。"
            action={
              <Button asChild variant="outline">
                <Link href="/alerts">配置告警</Link>
              </Button>
            }
          />
        ))}
    </UI.Content>
  );
}

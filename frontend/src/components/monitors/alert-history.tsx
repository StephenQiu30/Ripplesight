"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { listAlertHistory } from "@/api/gerentufagaojing";
import { PageState } from "@/components/system/page-state";
import * as UI from "@/components/ui/content";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
import { Separator } from "@/components/ui/separator";
import { ApiRequestError } from "@/request";
import { alertHistoryStatusLabels, alertReasonLabel } from "./alert-presenters";
import { readMonitorFailure, type MonitorFailure } from "./monitor-presenters";

export function AlertHistory({ ruleId }: { ruleId: string }) {
  const [rows, setRows] = useState<HotKeyAPI.AlertEvaluationView[] | null>(
    null,
  );
  const [error, setError] = useState<MonitorFailure | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const generation = useRef(0);
  const load = useCallback(() => {
    const request = ++generation.current;
    return listAlertHistory({ rule_id: ruleId, limit: 50 })
      .then((page) => {
        if (generation.current === request) {
          setRows(page);
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (caught instanceof ApiRequestError && caught.kind === "cancelled")
          return;
        if (generation.current === request)
          setError(readMonitorFailure(caught, "告警历史读取失败，请重试。"));
      })
      .finally(() => {
        if (generation.current === request) setRefreshing(false);
      });
  }, [ruleId]);
  useEffect(() => {
    void load();
    return () => {
      generation.current += 1;
    };
  }, [load]);
  function refresh() {
    setRefreshing(true);
    void load();
  }
  const retry = (
    <Button
      type="button"
      variant="outline"
      disabled={refreshing}
      onClick={refresh}
    >
      重试历史
    </Button>
  );
  if (error?.forbidden)
    return (
      <PageState
        headingLevel={2}
        state="forbidden"
        eyebrow="告警历史"
        title="无权读取告警历史"
        description="请登录有权访问这条规则的账户。"
      />
    );
  return (
    <UI.Content
      className="flex min-w-0 flex-col gap-4"
      aria-label="告警评估历史"
    >
      {error && (
        <PageState
          headingLevel={2}
          state={rows ? "stale" : "error"}
          eyebrow="告警历史"
          title="暂时无法读取告警历史"
          description="请重试读取历史；当前输入会保留。"
          errorCode={error.code}
          httpStatus={error.httpStatus}
          action={retry}
        />
      )}
      {!rows && !error && (
        <PageState
          headingLevel={2}
          state="loading"
          eyebrow="告警历史"
          title="正在读取评估历史"
          description="正在读取规则的最近评估记录。"
        />
      )}
      {rows && !rows.length && (
        <PageState
          headingLevel={2}
          state="empty"
          eyebrow="告警历史"
          title="尚无评估记录"
          description="启用后每五分钟评估一次；条件不足会保留原因。"
          action={
            <Button
              type="button"
              variant="outline"
              disabled={refreshing}
              onClick={refresh}
            >
              刷新历史
            </Button>
          }
        />
      )}
      {rows && rows.length > 0 && (
        <>
          <UI.Content className="flex flex-wrap items-center justify-between gap-3">
            <UI.Text size="xs" tone="muted">
              最近 {rows.length} 条评估记录（最多 50 条）
            </UI.Text>
            <Button
              type="button"
              variant="ghost"
              size="navigation"
              disabled={refreshing}
              aria-busy={refreshing}
              onClick={refresh}
            >
              刷新历史
            </Button>
          </UI.Content>
          <ItemGroup>
            {rows.map((item) => (
              <UI.Content
                key={item.id}
                role="listitem"
                className="flex flex-col gap-3"
              >
                <Separator />
                <Item className="px-0">
                  <ItemContent className="min-w-0 gap-3">
                    <UI.Content className="flex flex-wrap items-center gap-3">
                      <Badge variant="secondary">
                        {alertHistoryStatusLabels[item.status]}
                      </Badge>
                      <UI.Text size="xs" tone="muted">
                        <UI.InlineCode>
                          <UI.Timestamp dateTime={item.window_end}>
                            {new Date(item.window_end).toLocaleString("zh-CN")}
                          </UI.Timestamp>
                        </UI.InlineCode>
                      </UI.Text>
                    </UI.Content>
                    <UI.Text size="sm">
                      指标：
                      <UI.InlineCode>
                        {item.value === null ? "未知" : item.value}
                      </UI.InlineCode>{" "}
                      · 规则版本{" "}
                      <UI.InlineCode>{item.rule_version}</UI.InlineCode>
                    </UI.Text>
                    {item.reason && (
                      <UI.Text size="sm" tone="muted">
                        {alertReasonLabel(item.reason)}
                      </UI.Text>
                    )}
                    {item.cooldown_until && (
                      <UI.Text size="xs" tone="muted">
                        冷却至{" "}
                        <UI.InlineCode>
                          {new Date(item.cooldown_until).toLocaleString(
                            "zh-CN",
                          )}
                        </UI.InlineCode>
                      </UI.Text>
                    )}
                  </ItemContent>
                </Item>
              </UI.Content>
            ))}
          </ItemGroup>
        </>
      )}
    </UI.Content>
  );
}

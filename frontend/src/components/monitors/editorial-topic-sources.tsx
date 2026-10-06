"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { listMonitorEditorialSources } from "@/api/jiankongzhuti";
import { PageState } from "@/components/system/page-state";
import { readMonitorFailure, type MonitorFailure } from "./monitor-presenters";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { ApiRequestError } from "@/request";

type Props = {
  selectedProfileIds: string[];
  onChange: (ids: string[]) => void;
  disabled: boolean;
};
type SourcesState =
  | { status: "loading" }
  | { status: "ready"; items: HotKeyAPI.EditorialTopicSourceView[] }
  | ({ status: "error" } & MonitorFailure);

export function EditorialTopicSources({
  selectedProfileIds,
  onChange,
  disabled,
}: Props) {
  const [state, setState] = useState<SourcesState>({ status: "loading" });
  const request = useRef(0);

  const loadSources = useCallback(() => {
    const current = ++request.current;
    return listMonitorEditorialSources()
      .then((items) => {
        if (current === request.current) setState({ status: "ready", items });
      })
      .catch((error: unknown) => {
        if (current !== request.current) return;
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        const message =
          error instanceof ApiRequestError
            ? error.message
            : "订阅流暂时无法读取，请稍后重试。";
        setState({ status: "error", ...readMonitorFailure(error, message) });
        toast.error(message);
      });
  }, []);

  useEffect(() => {
    const pending = request;
    void loadSources();
    return () => {
      ++pending.current;
    };
  }, [loadSources]);

  function toggle(id: string, selected: boolean) {
    onChange(
      selected
        ? Array.from(new Set([...selectedProfileIds, id])).sort()
        : selectedProfileIds.filter((value) => value !== id),
    );
  }

  const items = state.status === "ready" ? state.items : [];
  const known = new Set(items.map((item) => item.profile_id));
  const unavailable = selectedProfileIds.filter((id) => !known.has(id));

  return (
    <FieldSet disabled={disabled}>
      <FieldLegend variant="label">订阅流</FieldLegend>
      <FieldDescription>
        从已获准的订阅流中匹配关键词。一次更新可用于多个关注；筛选已有订阅内容的范围以来源说明为准。
      </FieldDescription>
      {state.status === "loading" ? (
        <Spinner aria-label="正在读取订阅流" />
      ) : state.status === "error" ? (
        <PageState
          state={state.forbidden ? "forbidden" : "error"}
          eyebrow="订阅流"
          title="订阅流暂时不可用"
          description="已选订阅流会保留。重新读取后可继续修改。"
          errorCode={state.code}
          httpStatus={state.httpStatus}
          action={
            state.forbidden ? undefined : (
              <Button
                type="button"
                variant="outline"
                disabled={disabled}
                onClick={() => {
                  setState({ status: "loading" });
                  void loadSources();
                }}
              >
                重新读取订阅流
              </Button>
            )
          }
        />
      ) : (
        <FieldGroup className="gap-5">
          {items.map((item) => {
            const selected = selectedProfileIds.includes(item.profile_id);
            return (
              <Field key={item.profile_id} orientation="horizontal">
                <Switch
                  id={`editorial-profile-${item.profile_id}`}
                  checked={selected}
                  disabled={disabled || (!item.selectable && !selected)}
                  onCheckedChange={(checked) =>
                    toggle(item.profile_id, checked)
                  }
                  aria-describedby={`editorial-profile-${item.profile_id}-reason`}
                />
                <FieldContent>
                  <FieldLabel htmlFor={`editorial-profile-${item.profile_id}`}>
                    {item.name}
                  </FieldLabel>
                  <FieldDescription
                    id={`editorial-profile-${item.profile_id}-reason`}
                  >
                    {sourceReason(item.reason)}
                    {` 每 ${item.interval_minutes} 分钟检查更新。`}
                    {item.text_scope === "summary" ||
                    item.text_scope === "excerpt"
                      ? "阅读范围为来源摘要。"
                      : item.text_scope === "description"
                        ? "阅读范围为作品描述。"
                        : item.text_scope === "metadata"
                          ? "阅读范围为标题和链接。"
                          : item.text_scope === "full"
                            ? "正文按当前来源许可读取。"
                            : "文本范围以每条材料说明为准。"}
                  </FieldDescription>
                </FieldContent>
              </Field>
            );
          })}
          {unavailable.map((id) => (
            <Field key={id} orientation="horizontal">
              <Switch
                id={`editorial-profile-${id}`}
                checked
                disabled={disabled}
                onCheckedChange={() => toggle(id, false)}
              />
              <FieldContent>
                <FieldLabel htmlFor={`editorial-profile-${id}`}>
                  当前不可用的订阅流
                </FieldLabel>
                <FieldDescription>
                  已选来源当前不可读取，可取消选择。保存时服务端会再次核验。
                </FieldDescription>
              </FieldContent>
            </Field>
          ))}
          {!items.length && !unavailable.length && (
            <FieldDescription>
              还没有获准的订阅流。可以先保存关注，来源准备好后再选择。
            </FieldDescription>
          )}
        </FieldGroup>
      )}
    </FieldSet>
  );
}

function sourceReason(reason: string | null | undefined): string {
  if (!reason) return "可在此订阅流中匹配主题关键词。";
  const labels: Record<string, string> = {
    editorial_source_disabled: "此订阅流已暂停。",
    connection_disabled: "此订阅流的连接已停用。",
    connection_version_conflict: "连接已更新，订阅流需要重新核验。",
    editorial_version_conflict: "来源配置已更新，需要重新核验。",
    source_policy_unavailable: "当前读取许可尚未满足。",
    rsshub_route_review_required: "此订阅入口正在等待准入核验。",
    rsshub_review_expired: "此订阅入口需要重新核验。",
    source_run_review_required: "上次采集结果不明，需要人工核查。",
    free_only_paid_source: "此入口超出当前免费接入范围。",
    external_ingest_only: "此来源仅接收导入材料。",
    editorial_participation_required: "此入口尚未用于个人主题订阅。",
  };
  return labels[reason] ?? "当前来源条件尚未满足，暂不可选。";
}

"use client";
import { AlertDescription, Alert } from "@/components/ui/alert";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { toast } from "sonner";
import {
  SelectLabel,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from "@/components/ui/select";
import { ChevronDownIcon } from "lucide-react";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { Checkbox } from "@/components/ui/checkbox";
import { FieldGroup, FieldLabel, Field } from "@/components/ui/field";
import Link from "next/link";
import { useId, useEffect, useRef, useState } from "react";
import {
  getOperationsHealth,
  getOperatorMaintenance,
  listOperatorFeedback,
  listOperatorAudit,
  listOperatorDictionaries,
  saveOperatorDictionary,
  updateOperatorBudget,
  updateOperatorFeedback,
  getOperatorFeedbackAttachment,
  runOperatorMaintenance,
  resolveOperatorDelivery,
} from "@/api/yunyingweihu";
import { NotificationWorkspace } from "./notification-workspace";
import { SourceIdentityEditor } from "./source-identity-editor";
import { SelectBenchReading } from "./selectbench-reading";
import { RelationBench } from "./relation-bench";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError, type RequestOptions } from "@/request";

const labels: Record<string, string> = {
  lifecycle_sweep: "到期清理",
  recover: "任务恢复",
  alerts: "故障告警",
  digest: "运营日报",
  source_health: "来源周检",
  feedback_forward: "反馈转发",
  backup: "创建备份",
  verify_backup: "隔离恢复验证",
  retention: "保留期清理",
  watchdog: "独立心跳检查",
};
function explain(error: unknown) {
  return error instanceof ApiRequestError
    ? `${error.message}${error.requestId ? `（请求 ${error.requestId}）` : ""}`
    : "操作失败，请保留输入并重试。";
}
function useOperationIdentity() {
  const attempts = useRef(new Map<string, { payload: string; id: string }>());
  return {
    id(key: string, input: unknown) {
      const payload = JSON.stringify(input);
      if (attempts.current.get(key)?.payload !== payload)
        attempts.current.set(key, { payload, id: crypto.randomUUID() });
      return attempts.current.get(key)!.id;
    },
    done(key: string) {
      attempts.current.delete(key);
    },
    clear() {
      attempts.current.clear();
    },
  };
}
function BudgetEditor({
  row,
  options,
  saved,
}: {
  row: HotKeyAPI.BudgetWindowUsageView;
  options: RequestOptions;
  saved: () => Promise<void>;
}) {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const fieldId = useId();

  const [limit, setLimit] = useState(String(row.limit_units));
  const [window, setWindow] = useState(String(row.window_seconds));
  const [enabled, setEnabled] = useState(row.enabled);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);

  const operation = useOperationIdentity();
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    try {
      const input = {
        expected_policy_version: row.policy_version,
        reason,
        policy: {
          budget_key: row.budget_key,
          metric: row.metric,
          scope_kind: row.scope_kind,
          scope_reference: row.scope_reference,
          limit_units: Number(limit),
          window_seconds: Number(window),
          window_anchor_at: row.window_anchor_at,
          enabled,
        },
      };
      await updateOperatorBudget(
        { ...input, operation_id: operation.id("budget", input) },
        options,
      );
      operation.done("budget");
      if (mounted.current) toast.success("预算已保存。");
      await saved();
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (mounted.current) toast.error(explain(error));
    } finally {
      setPending(false);
    }
  }
  return (
    <form onSubmit={submit}>
      <Item variant="muted" asChild>
        <FieldGroup className="grid gap-3 p-4 sm:grid-cols-2">
          <p className="break-all sm:col-span-2">
            {row.budget_key} · {row.metric} · {row.scope_kind}
            {row.scope_reference ? `:${row.scope_reference}` : ""}
            <span className="text-muted-foreground block text-sm">
              已用 {row.used_units} · 预留 {row.reserved_units} · 剩余{" "}
              {row.remaining_units} · 版本 {row.policy_version}
            </span>
          </p>
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-operations-workspace-field-1`}>
              上限
            </FieldLabel>
            <Input
              aria-label={`${row.budget_key} 上限`}
              type="number"
              required
              min={1}
              step={1}
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              id={`${fieldId}-operations-workspace-field-1`}
            />
          </Field>
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-operations-workspace-field-2`}>
              窗口（秒）
            </FieldLabel>
            <Input
              type="number"
              required
              min={1}
              step={1}
              value={window}
              onChange={(e) => setWindow(e.target.value)}
              id={`${fieldId}-operations-workspace-field-2`}
            />
          </Field>
          <Field className="min-w-0 sm:col-span-2">
            <FieldLabel htmlFor={`${fieldId}-operations-workspace-field-3`}>
              修改原因
            </FieldLabel>
            <Input
              required
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              id={`${fieldId}-operations-workspace-field-3`}
            />
          </Field>
          <Field orientation="horizontal" className="w-auto">
            <Checkbox
              checked={enabled}
              onCheckedChange={(checked) => setEnabled(checked === true)}
              id={`${fieldId}-operations-workspace-field-4`}
            />
            <FieldLabel htmlFor={`${fieldId}-operations-workspace-field-4`}>
              启用硬预算
            </FieldLabel>
          </Field>
          <Button
            disabled={pending}
            type="submit"
            className="justify-self-start"
          >
            保存预算
          </Button>
        </FieldGroup>
      </Item>
    </form>
  );
}
function BudgetCreator({
  options,
  saved,
}: {
  options: RequestOptions;
  saved: () => Promise<void>;
}) {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const fieldId = useId();

  const [key, setKey] = useState("");
  const [metric, setMetric] =
    useState<HotKeyAPI.BudgetMetric>("network_request");
  const [scope, setScope] = useState<HotKeyAPI.BudgetScopeKind>("global");
  const [ref, setRef] = useState("");
  const [limit, setLimit] = useState("100");
  const [window, setWindow] = useState("3600");
  const [anchor] = useState(() => new Date().toISOString());
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);

  const operation = useOperationIdentity();
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    try {
      const input = {
        expected_policy_version: 0,
        reason,
        policy: {
          budget_key: key,
          metric,
          scope_kind: scope,
          scope_reference: scope === "global" ? null : ref,
          limit_units: Number(limit),
          window_seconds: Number(window),
          window_anchor_at: anchor,
          enabled: true,
        },
      };
      await updateOperatorBudget(
        { ...input, operation_id: operation.id("create-budget", input) },
        options,
      );
      operation.done("create-budget");
      setKey("");
      if (mounted.current) toast.success("预算已创建。");
      await saved();
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (mounted.current) toast.error(explain(error));
    } finally {
      setPending(false);
    }
  }
  return (
    <Item variant="muted" asChild>
      <Collapsible className="p-4">
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
          >
            <span className="min-w-0 text-left">创建预算政策</span>
            <ChevronDownIcon
              aria-hidden="true"
              data-icon="inline-end"
              className="group-data-[state=open]:rotate-180"
            />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent forceMount className="data-[state=closed]:hidden">
          <form onSubmit={submit}>
            <FieldGroup className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field className="min-w-0">
                <FieldLabel htmlFor={`${fieldId}-operations-workspace-field-5`}>
                  预算名称
                </FieldLabel>
                <Input
                  required
                  pattern="[a-z][a-z0-9_.:-]*"
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  id={`${fieldId}-operations-workspace-field-5`}
                />
              </Field>
              <Field className="min-w-0">
                <FieldLabel htmlFor={`${fieldId}-operations-workspace-field-6`}>
                  计量单位
                </FieldLabel>
                <Select
                  value={metric}
                  onValueChange={(selectedValue) =>
                    setMetric(selectedValue as HotKeyAPI.BudgetMetric)
                  }
                >
                  <SelectTrigger
                    id={`${fieldId}-operations-workspace-field-6`}
                    className="w-full min-w-0"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent position="popper">
                    <SelectGroup>
                      <SelectLabel className="sr-only">计量单位</SelectLabel>
                      {(
                        [
                          "network_request",
                          "collector_call",
                          "analysis_attempt",
                          "concurrency_slot",
                          "x_api_usd_micros",
                          "provider_cny_micros",
                          "provider_usd_micros",
                        ] as const
                      ).map((value) => (
                        <SelectItem
                          key={value}
                          value={value}
                          className="whitespace-normal"
                        >
                          {value}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              <Field className="min-w-0">
                <FieldLabel htmlFor={`${fieldId}-operations-workspace-field-7`}>
                  范围
                </FieldLabel>
                <Select
                  value={scope}
                  onValueChange={(selectedValue) =>
                    setScope(selectedValue as HotKeyAPI.BudgetScopeKind)
                  }
                >
                  <SelectTrigger
                    id={`${fieldId}-operations-workspace-field-7`}
                    className="w-full min-w-0"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent position="popper">
                    <SelectGroup>
                      <SelectLabel className="sr-only">范围</SelectLabel>
                      {(["global", "source", "connection", "job"] as const).map(
                        (value) => (
                          <SelectItem
                            key={value}
                            value={value}
                            className="whitespace-normal"
                          >
                            {value}
                          </SelectItem>
                        ),
                      )}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              {scope !== "global" && (
                <Field className="min-w-0">
                  <FieldLabel
                    htmlFor={`${fieldId}-operations-workspace-field-8`}
                  >
                    范围引用
                  </FieldLabel>
                  <Input
                    required
                    value={ref}
                    onChange={(e) => setRef(e.target.value)}
                    id={`${fieldId}-operations-workspace-field-8`}
                  />
                </Field>
              )}
              <Field className="min-w-0">
                <FieldLabel htmlFor={`${fieldId}-operations-workspace-field-9`}>
                  创建预算上限
                </FieldLabel>
                <Input
                  required
                  type="number"
                  min={1}
                  step={1}
                  value={limit}
                  onChange={(e) => setLimit(e.target.value)}
                  id={`${fieldId}-operations-workspace-field-9`}
                />
              </Field>
              <Field className="min-w-0">
                <FieldLabel
                  htmlFor={`${fieldId}-operations-workspace-field-10`}
                >
                  创建预算窗口（秒）
                </FieldLabel>
                <Input
                  required
                  type="number"
                  min={1}
                  step={1}
                  value={window}
                  onChange={(e) => setWindow(e.target.value)}
                  id={`${fieldId}-operations-workspace-field-10`}
                />
              </Field>
              <Field className="min-w-0 sm:col-span-2">
                <FieldLabel
                  htmlFor={`${fieldId}-operations-workspace-field-11`}
                >
                  创建预算原因
                </FieldLabel>
                <Input
                  required
                  maxLength={2000}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  id={`${fieldId}-operations-workspace-field-11`}
                />
              </Field>
              <Button type="submit" disabled={pending}>
                创建硬预算
              </Button>
            </FieldGroup>
          </form>
        </CollapsibleContent>
      </Collapsible>
    </Item>
  );
}

function FeedbackReview({
  row,
  options,
  saved,
  active,
}: {
  row: HotKeyAPI.FeedbackView;
  options: RequestOptions;
  saved: () => Promise<void>;
  active: () => boolean;
}) {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const fieldId = useId();

  const [status, setStatus] = useState(row.status);
  const [note, setNote] = useState(row.note ?? "");
  const [reason, setReason] = useState("");
  const [banned, setBanned] = useState(row.banned);

  const [pending, setPending] = useState(false);
  const operation = useOperationIdentity();
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    try {
      const input = {
        expected_revision: row.revision,
        status,
        note: note || null,
        reason,
        banned,
      };
      await updateOperatorFeedback(
        { feedback_id: row.id },
        { ...input, operation_id: operation.id("feedback", input) },
        options,
      );
      operation.done("feedback");
      await saved();
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (mounted.current) toast.error(explain(error));
    } finally {
      setPending(false);
    }
  }
  async function screenshot() {
    if (!row.attachment_id || !active()) return;
    try {
      const result = await getOperatorFeedbackAttachment(
        { attachment_id: row.attachment_id },
        { ...options, responseType: "blob" },
      );
      if (!active()) return;
      if (!(result instanceof Blob)) throw new Error("unexpected attachment");
      const url = URL.createObjectURL(result);
      const link = document.createElement("a");
      link.href = url;
      link.download = `feedback-${row.id}.${row.attachment_mime?.split("/")[1] ?? "image"}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (mounted.current) toast.error(explain(error));
    }
  }
  return (
    <Item variant="muted" asChild>
      <article className="grid gap-3 p-4">
        <ItemContent className="min-w-0 gap-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="text-sm break-all">
              {row.id} · {row.status} · 版本 {row.revision}
              <span className="text-muted-foreground block">
                {row.created_at} · 转发{" "}
                {row.forwarded_at ?? row.forward_error ?? "未发送"}
              </span>
            </p>
            {row.attachment_id && (
              <Button variant="ghost" onClick={screenshot}>
                下载私有截图
              </Button>
            )}
          </div>
          <p className="break-words whitespace-pre-wrap">
            {row.content ?? "内容已删除"}
          </p>
          {row.email && <p className="text-sm break-all">{row.email}</p>}
          {row.page_url && (
            <a
              className="text-sm break-all underline"
              href={row.page_url}
              target="_blank"
              rel="noreferrer"
            >
              相关页面
            </a>
          )}
          <form onSubmit={submit}>
            <FieldGroup className="grid gap-3 sm:grid-cols-2">
              <Field className="min-w-0">
                <FieldLabel
                  htmlFor={`${fieldId}-operations-workspace-field-12`}
                >
                  处理状态
                </FieldLabel>
                <Select
                  value={status}
                  onValueChange={(selectedValue) =>
                    setStatus(selectedValue as HotKeyAPI.FeedbackView["status"])
                  }
                >
                  <SelectTrigger
                    aria-label="反馈处理状态"
                    id={`${fieldId}-operations-workspace-field-12`}
                    className="w-full min-w-0"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent position="popper">
                    <SelectGroup>
                      <SelectLabel className="sr-only">处理状态</SelectLabel>
                      {[
                        "new",
                        "reviewing",
                        "resolved",
                        "rejected",
                        "deleted",
                      ].map((value) => (
                        <SelectItem
                          key={value}
                          value={value}
                          className="whitespace-normal"
                        >
                          {value}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              <Field orientation="horizontal" className="w-auto">
                <Checkbox
                  checked={banned}
                  onCheckedChange={(checked) => setBanned(checked === true)}
                  id={`${fieldId}-operations-workspace-field-13`}
                />
                <FieldLabel
                  htmlFor={`${fieldId}-operations-workspace-field-13`}
                >
                  封禁此匿名来源
                </FieldLabel>
              </Field>
              <Field className="min-w-0 sm:col-span-2">
                <FieldLabel
                  htmlFor={`${fieldId}-operations-workspace-field-14`}
                >
                  处理备注
                </FieldLabel>
                <Textarea
                  maxLength={2000}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  id={`${fieldId}-operations-workspace-field-14`}
                />
              </Field>
              <Field className="min-w-0 sm:col-span-2">
                <FieldLabel
                  htmlFor={`${fieldId}-operations-workspace-field-15`}
                >
                  操作原因
                </FieldLabel>
                <Input
                  required
                  maxLength={2000}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  id={`${fieldId}-operations-workspace-field-15`}
                />
              </Field>
              <Button
                disabled={pending}
                type="submit"
                className="justify-self-start"
              >
                保存反馈处置
              </Button>
            </FieldGroup>
          </form>
          {status === "deleted" && (
            <ItemDescription className="line-clamp-none">
              保存后会清除正文、联系方式和截图。
            </ItemDescription>
          )}
        </ItemContent>
      </article>
    </Item>
  );
}
function DictionaryEditor({
  rows,
  options,
  saved,
}: {
  rows: HotKeyAPI.DictionaryView[];
  options: RequestOptions;
  saved: () => Promise<void>;
}) {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const fieldId = useId();

  const [kind, setKind] =
    useState<HotKeyAPI.DictionaryInput["kind"]>("glossary");
  const [text, setText] = useState(
    JSON.stringify(
      rows.find((row) => row.kind === "glossary")?.content ?? {},
      null,
      2,
    ),
  );
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);

  const operation = useOperationIdentity();
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    try {
      const content: HotKeyAPI.DictionaryInput["content"] = JSON.parse(text);
      const input = {
        kind,
        content,
        expected_version: rows.find((row) => row.kind === kind)?.version ?? 0,
        reason,
      };
      await saveOperatorDictionary(
        { ...input, operation_id: operation.id("dictionary", input) },
        options,
      );
      operation.done("dictionary");
      if (mounted.current) toast.success("词典新版本已保存。");
      await saved();
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (mounted.current)
        toast.error(
          error instanceof SyntaxError
            ? "词典需要有效 JSON：名称对应别名数组。"
            : explain(error),
        );
    } finally {
      setPending(false);
    }
  }
  return (
    <section className="grid gap-4">
      <h2 className="text-xl font-semibold">词典版本</h2>
      <form onSubmit={submit}>
        <FieldGroup className="grid gap-3">
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-operations-workspace-field-16`}>
              词典
            </FieldLabel>
            <Select
              value={kind}
              onValueChange={(selectedValue) => {
                const value =
                  selectedValue as HotKeyAPI.DictionaryInput["kind"];
                setKind(value);
                setText(
                  JSON.stringify(
                    rows.find((row) => row.kind === value)?.content ?? {},
                    null,
                    2,
                  ),
                );
              }}
            >
              <SelectTrigger
                aria-label="词典类型"
                id={`${fieldId}-operations-workspace-field-16`}
                className="w-full min-w-0"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper">
                <SelectGroup>
                  <SelectLabel className="sr-only">词典</SelectLabel>
                  {["glossary", "entities", "categories"].map((value) => (
                    <SelectItem
                      key={value}
                      value={value}
                      className="whitespace-normal"
                    >
                      {value}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </Field>
          <p className="text-sm">
            当前版本{" "}
            {rows.find((row) => row.kind === kind)?.version ?? "尚未创建"}
          </p>
          <Textarea
            aria-label="词典内容"
            rows={8}
            required
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-operations-workspace-field-17`}>
              词典修改原因
            </FieldLabel>
            <Input
              aria-label="词典修改原因"
              required
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              id={`${fieldId}-operations-workspace-field-17`}
            />
          </Field>
          <Button
            disabled={pending}
            type="submit"
            className="justify-self-start"
          >
            保存词典新版本
          </Button>
        </FieldGroup>
      </form>
    </section>
  );
}
function AuditResolution({
  row,
  options,
  saved,
}: {
  row: HotKeyAPI.OperatorAuditView;
  options: RequestOptions;
  saved: () => Promise<void>;
}) {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const [outcome, setOutcome] =
    useState<HotKeyAPI.AuditResolutionInput["outcome"]>("not_delivered");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);

  const operation = useOperationIdentity();
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    try {
      const input = { outcome, reason };
      await resolveOperatorDelivery(
        { audit_id: row.id },
        { ...input, operation_id: operation.id("resolve", input) },
        options,
      );
      operation.done("resolve");
      await saved();
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (mounted.current) toast.error(explain(error));
    } finally {
      setPending(false);
    }
  }
  return (
    <form onSubmit={submit}>
      <FieldGroup className="mt-3 grid gap-3">
        <p className="text-sm">
          请先在目的地核对实际投递；核对结果不会自动再次发送。
        </p>
        <Select
          value={outcome}
          onValueChange={(selectedValue) =>
            setOutcome(
              selectedValue as HotKeyAPI.AuditResolutionInput["outcome"],
            )
          }
        >
          <SelectTrigger
            aria-label="未知投递核对结果"
            className="w-full min-w-0"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent position="popper">
            <SelectGroup>
              <SelectLabel className="sr-only">未知投递核对结果</SelectLabel>
              <SelectItem value="not_delivered" className="whitespace-normal">
                确认未送达
              </SelectItem>
              <SelectItem value="delivered" className="whitespace-normal">
                确认已送达
              </SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <Input
          aria-label="投递核对证据"
          placeholder="核对依据与原因"
          required
          maxLength={2000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <Button type="submit" disabled={pending} className="justify-self-start">
          记录投递核对
        </Button>
      </FieldGroup>
    </form>
  );
}

export function OperationsWorkspace() {
  const fieldId = useId();

  const [input, setInput] = useState("");
  const [token, setToken] = useState("");
  const [health, setHealth] = useState<HotKeyAPI.OperationsHealthView | null>(
    null,
  );
  const [maintenance, setMaintenance] =
    useState<HotKeyAPI.MaintenanceStateView | null>(null);
  const [feedback, setFeedback] = useState<HotKeyAPI.FeedbackView[]>([]);
  const [audits, setAudits] = useState<HotKeyAPI.OperatorAuditView[]>([]);
  const [dictionaries, setDictionaries] = useState<HotKeyAPI.DictionaryView[]>(
    [],
  );

  const [pending, setPending] = useState(false);
  const [action, setAction] =
    useState<HotKeyAPI.MaintenanceInput["action"]>("recover");
  const [reason, setReason] = useState("");
  const [backupId, setBackupId] = useState("");
  const [feedbackCursor, setFeedbackCursor] = useState<string | null>(null);
  const [auditCursor, setAuditCursor] = useState<string | null>(null);
  const operation = useOperationIdentity();
  const access = useRef({ epoch: 0, token: "" });
  const [accessEpoch, setAccessEpoch] = useState(0);
  const refreshSequence = useRef(0);
  useEffect(
    () => () => {
      access.current = { epoch: access.current.epoch + 1, token: "" };
    },
    [],
  );
  const options = { headers: { "X-HotKey-Operator-Token": token } };
  function isCurrent(currentToken: string, captured: number) {
    return (
      !!currentToken &&
      access.current.epoch === captured &&
      access.current.token === currentToken
    );
  }
  function clearAccess(nextInput = "") {
    const epoch = access.current.epoch + 1;
    access.current = { epoch, token: "" };
    refreshSequence.current += 1;
    setAccessEpoch(epoch);
    operation.clear();
    setToken("");
    setInput(nextInput);
    setHealth(null);
    setFeedback([]);
    setFeedbackCursor(null);
    setAudits([]);
    setAuditCursor(null);
    setMaintenance(null);
    setDictionaries([]);
    setReason("");
    setBackupId("");

    setPending(false);
  }
  function enter() {
    const currentToken = input.trim();
    if (!currentToken) return;
    const epoch = access.current.epoch + 1;
    access.current = { epoch, token: currentToken };
    setAccessEpoch(epoch);
    void refresh(currentToken, epoch);
  }
  async function refresh(currentToken = token, captured = accessEpoch) {
    // A child mutation may retain this callback after exit or a different login.
    if (!isCurrent(currentToken, captured)) return;
    const sequence = ++refreshSequence.current;
    const current = () =>
      isCurrent(currentToken, captured) && sequence === refreshSequence.current;
    setPending(true);

    const request = { headers: { "X-HotKey-Operator-Token": currentToken } };
    try {
      const [health, state, feedback, audit, dictionaries] = await Promise.all([
        getOperationsHealth(request),
        getOperatorMaintenance(request),
        listOperatorFeedback({ limit: 20 }, request),
        listOperatorAudit({ limit: 20 }, request),
        listOperatorDictionaries(request),
      ]);
      if (!current()) return;
      setHealth(health);
      setMaintenance(state);
      setFeedback(feedback.items);
      setFeedbackCursor(feedback.next_cursor);
      setAudits(audit.items);
      setAuditCursor(audit.next_cursor);
      setDictionaries(dictionaries);
      setToken(currentToken);
      setInput("");
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (current()) toast.error(explain(error));
    } finally {
      if (current()) setPending(false);
    }
  }
  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!isCurrent(token, accessEpoch)) return;
    const currentToken = token,
      captured = accessEpoch;
    setPending(true);
    try {
      const payload = {
        action,
        reason,
        backup_id: action === "verify_backup" ? backupId : null,
      };
      const job = await runOperatorMaintenance(
        { ...payload, operation_id: operation.id("maintenance", payload) },
        options,
      );
      if (!isCurrent(currentToken, captured)) return;
      operation.done("maintenance");
      toast.success(`维护任务已受理：${job.job_id}。执行结果请刷新审计。`);
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (isCurrent(currentToken, captured)) toast.error(explain(error));
    } finally {
      if (isCurrent(currentToken, captured)) setPending(false);
    }
  }
  async function moreFeedback() {
    if (!isCurrent(token, accessEpoch)) return;
    const currentToken = token,
      captured = accessEpoch;
    try {
      const page = await listOperatorFeedback(
        { cursor: feedbackCursor, limit: 20 },
        options,
      );
      if (!isCurrent(currentToken, captured)) return;
      setFeedback((v) => [...v, ...page.items]);
      setFeedbackCursor(page.next_cursor);
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (isCurrent(currentToken, captured)) toast.error(explain(error));
    }
  }
  async function moreAudit() {
    if (!isCurrent(token, accessEpoch)) return;
    const currentToken = token,
      captured = accessEpoch;
    try {
      const page = await listOperatorAudit(
        { cursor: auditCursor, limit: 20 },
        options,
      );
      if (!isCurrent(currentToken, captured)) return;
      setAudits((v) => [...v, ...page.items]);
      setAuditCursor(page.next_cursor);
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (isCurrent(currentToken, captured)) toast.error(explain(error));
    }
  }
  return (
    <>
      <div className="grid gap-10">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold">运营管理</h1>
            <p className="text-muted-foreground mt-2 text-sm">
              独立运营权限 · Token 仅保留在当前页面内存
            </p>
          </div>
          <Link href="/feedback" className="text-sm underline">
            打开反馈入口
          </Link>
        </div>
        {!token ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              enter();
            }}
          >
            <FieldGroup className="grid max-w-lg gap-4">
              <Field className="min-w-0">
                <FieldLabel
                  htmlFor={`${fieldId}-operations-workspace-field-18`}
                >
                  运营 Token
                </FieldLabel>
                <Input
                  aria-label="运营 Token"
                  type="password"
                  autoComplete="off"
                  required
                  maxLength={512}
                  value={input}
                  onChange={(e) => clearAccess(e.target.value)}
                  id={`${fieldId}-operations-workspace-field-18`}
                />
              </Field>
              <Button
                type="submit"
                disabled={pending}
                className="justify-self-start"
              >
                进入运营工作区
              </Button>
            </FieldGroup>
          </form>
        ) : (
          <div className="flex gap-2">
            <Button disabled={pending} onClick={() => void refresh()}>
              刷新运营状态
            </Button>
            <Button variant="ghost" onClick={() => clearAccess()}>
              退出运营工作区
            </Button>
          </div>
        )}
        {token && health && (
          <>
            <section className="grid gap-5">
              <h2 className="text-xl font-semibold">进程与预算</h2>
              <div className="flex flex-wrap gap-4 text-sm">
                <span>
                  {health.maintenance_enabled
                    ? "维护调度已开启"
                    : "维护调度已关闭"}
                </span>
                <span>
                  {health.backup_configured ? "备份已配置" : "备份未配置"}
                </span>
                <span>
                  {health.feedback_forward_enabled
                    ? "反馈转发已开启"
                    : "反馈外部转发已关闭"}
                </span>
              </div>
              {health.heartbeats.length === 0 ? (
                <Empty>
                  <EmptyHeader>
                    <EmptyDescription>尚无真实进程心跳。</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {health.heartbeats.map((row) => (
                    <Alert role="note" key={row.instance_id} className="p-4">
                      <AlertDescription>
                        {row.role} · {row.state}
                        <span className="text-muted-foreground block text-sm">
                          PID {row.pid} · {row.age_seconds} 秒前
                        </span>
                      </AlertDescription>
                    </Alert>
                  ))}
                </div>
              )}
              {health.failure_issues.map((row) => (
                <pre
                  key={row.latest_failed_job_id}
                  className="bg-muted/40 overflow-auto rounded-lg p-3 text-xs"
                >
                  {JSON.stringify(row, null, 2)}
                </pre>
              ))}
              <div className="grid gap-4 lg:grid-cols-2">
                {health.budgets.map((row) => (
                  <BudgetEditor
                    key={`${row.budget_key}:${row.policy_version}`}
                    row={row}
                    options={options}
                    saved={() => refresh()}
                  />
                ))}
              </div>
              <BudgetCreator options={options} saved={() => refresh()} />
            </section>
            {maintenance && (
              <section className="grid gap-5">
                <h2 className="text-xl font-semibold">维护与恢复</h2>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {maintenance.schedules.map((row) => (
                    <Item variant="muted" key={row.action} asChild>
                      <div className="p-4">
                        <ItemContent className="min-w-0 gap-3">
                          <p>
                            {labels[row.action] ?? row.action} ·{" "}
                            {row.enabled ? "已启用" : "已关闭"}
                          </p>
                          <ItemDescription className="line-clamp-none">
                            间隔 {row.interval_seconds} 秒 · 最近{" "}
                            {row.latest_audit?.status ?? "无执行记录"}
                          </ItemDescription>
                        </ItemContent>
                      </div>
                    </Item>
                  ))}
                </div>
                {maintenance.schedules.map((row) => {
                  const report =
                    row.latest_audit?.after_state?.source_health_report;
                  if (
                    row.action !== "source_health" ||
                    typeof report !== "string"
                  )
                    return null;
                  return (
                    <Item variant="muted" key="source-health-report" asChild>
                      <section className="p-4">
                        <ItemContent className="min-w-0 gap-3">
                          <ItemTitle className="line-clamp-none w-full">
                            <h3>最近来源周报</h3>
                          </ItemTitle>
                          <ItemDescription className="mt-2 line-clamp-none whitespace-pre-wrap">
                            {report}
                          </ItemDescription>
                          <ItemDescription className="mt-2 line-clamp-none">
                            {row.latest_audit?.after_state?.delivered === true
                              ? "已保存渠道成功回执"
                              : row.latest_audit?.status === "unknown"
                                ? "渠道结果未知，请核对后处理"
                                : "本地报告已保存；请在审计中查看投递状态"}
                          </ItemDescription>
                        </ItemContent>
                      </section>
                    </Item>
                  );
                })}
                {maintenance.findings.map((row) => (
                  <Alert role="note" key={row.key} className="p-4">
                    <AlertDescription>
                      <strong>{row.title}</strong> · {row.severity}
                      <span className="text-muted-foreground block text-sm">
                        {row.detail}
                      </span>
                    </AlertDescription>
                  </Alert>
                ))}
                <form onSubmit={run}>
                  <FieldGroup className="grid gap-3 sm:grid-cols-2">
                    <Field className="min-w-0">
                      <FieldLabel
                        htmlFor={`${fieldId}-operations-workspace-field-19`}
                      >
                        维护操作
                      </FieldLabel>
                      <Select
                        value={action}
                        onValueChange={(selectedValue) =>
                          setAction(
                            selectedValue as HotKeyAPI.MaintenanceInput["action"],
                          )
                        }
                      >
                        <SelectTrigger
                          id={`${fieldId}-operations-workspace-field-19`}
                          className="w-full min-w-0"
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent position="popper">
                          <SelectGroup>
                            <SelectLabel className="sr-only">
                              维护操作
                            </SelectLabel>
                            {Object.entries(labels).map(([key, value]) => (
                              <SelectItem
                                key={key}
                                value={key}
                                className="whitespace-normal"
                              >
                                {value}
                              </SelectItem>
                            ))}
                          </SelectGroup>
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field className="min-w-0">
                      <FieldLabel
                        htmlFor={`${fieldId}-operations-workspace-field-20`}
                      >
                        维护原因
                      </FieldLabel>
                      <Input
                        required
                        maxLength={2000}
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        id={`${fieldId}-operations-workspace-field-20`}
                      />
                    </Field>
                    {action === "verify_backup" && (
                      <Field className="min-w-0 sm:col-span-2">
                        <FieldLabel
                          htmlFor={`${fieldId}-operations-workspace-field-21`}
                        >
                          备份编号
                        </FieldLabel>
                        <Input
                          required
                          value={backupId}
                          onChange={(e) => setBackupId(e.target.value)}
                          placeholder="已完成备份的 UUID"
                          id={`${fieldId}-operations-workspace-field-21`}
                        />
                      </Field>
                    )}
                    <Button
                      type="submit"
                      disabled={pending}
                      className="justify-self-start"
                    >
                      受理维护任务
                    </Button>
                  </FieldGroup>
                </form>
                <div className="grid gap-3">
                  {maintenance.backups.map((row) => (
                    <Item variant="muted" key={row.id} asChild>
                      <div className="p-4">
                        <ItemContent className="min-w-0 gap-3">
                          <p>
                            {row.action} · {row.status}
                          </p>
                          <pre className="mt-2 overflow-auto text-xs">
                            {JSON.stringify(row.after_state, null, 2)}
                          </pre>
                          {row.job_id && (
                            <Link
                              className="text-sm underline"
                              href={`/jobs/${row.job_id}`}
                            >
                              查看原任务
                            </Link>
                          )}
                        </ItemContent>
                      </div>
                    </Item>
                  ))}
                </div>
              </section>
            )}
            <section className="grid gap-5">
              <h2 className="text-xl font-semibold">反馈处置</h2>
              <p className="text-muted-foreground text-sm">
                新反馈 {health.feedback_new_count} · 处理中{" "}
                {health.feedback_reviewing_count}
              </p>
              {feedback.map((row) => (
                <FeedbackReview
                  key={`${row.id}:${row.revision}`}
                  row={row}
                  options={options}
                  saved={() => refresh()}
                  active={() => isCurrent(token, accessEpoch)}
                />
              ))}
              {feedback.length === 0 && (
                <Empty>
                  <EmptyHeader>
                    <EmptyDescription>暂无反馈。</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              )}
              {feedbackCursor && (
                <Button
                  variant="ghost"
                  className="justify-self-start"
                  onClick={moreFeedback}
                >
                  加载更多反馈
                </Button>
              )}
            </section>
            <DictionaryEditor
              key={dictionaries.map((row) => row.id).join()}
              rows={dictionaries}
              options={options}
              saved={() => refresh()}
            />
            <SourceIdentityEditor token={token} />
            <NotificationWorkspace token={token} />
            <SelectBenchReading token={token} />
            <RelationBench token={token} />
            <section className="grid gap-4">
              <h2 className="text-xl font-semibold">操作审计</h2>
              {audits.map((row) => (
                <Item variant="muted" key={row.id} asChild>
                  <article className="p-4">
                    <ItemContent className="min-w-0 gap-3">
                      <p className="break-all">
                        {row.action} · {row.status}
                        <span className="text-muted-foreground block text-sm">
                          {row.created_at} · {row.reason}
                        </span>
                      </p>
                      {row.error_code && (
                        <p className="text-sm">{row.error_code}</p>
                      )}
                      {row.job_id && (
                        <Link
                          className="text-sm underline"
                          href={`/jobs/${row.job_id}`}
                        >
                          查看原任务
                        </Link>
                      )}
                      {row.status === "unknown" && (
                        <AuditResolution
                          row={row}
                          options={options}
                          saved={() => refresh()}
                        />
                      )}
                    </ItemContent>
                  </article>
                </Item>
              ))}
              {auditCursor && (
                <Button
                  className="justify-self-start"
                  variant="ghost"
                  onClick={moreAudit}
                >
                  加载更多审计
                </Button>
              )}
            </section>
          </>
        )}
      </div>
    </>
  );
}

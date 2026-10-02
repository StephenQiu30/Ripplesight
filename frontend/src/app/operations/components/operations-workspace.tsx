"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
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
import { WorkspaceHeader } from "@/components/navigation/workspace-header";
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
  const [limit, setLimit] = useState(String(row.limit_units));
  const [window, setWindow] = useState(String(row.window_seconds));
  const [enabled, setEnabled] = useState(row.enabled);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
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
      setMessage("预算已保存。");
      await saved();
    } catch (error) {
      setMessage(explain(error));
    } finally {
      setPending(false);
    }
  }
  return (
    <form
      onSubmit={submit}
      className="bg-muted/40 grid gap-3 rounded-lg p-4 sm:grid-cols-2"
    >
      <p className="break-all sm:col-span-2">
        {row.budget_key} · {row.metric} · {row.scope_kind}
        {row.scope_reference ? `:${row.scope_reference}` : ""}
        <span className="text-muted-foreground block text-sm">
          已用 {row.used_units} · 预留 {row.reserved_units} · 剩余{" "}
          {row.remaining_units} · 版本 {row.policy_version}
        </span>
      </p>
      <label className="grid gap-1">
        上限
        <Input
          aria-label={`${row.budget_key} 上限`}
          type="number"
          required
          min={1}
          step={1}
          value={limit}
          onChange={(e) => setLimit(e.target.value)}
        />
      </label>
      <label className="grid gap-1">
        窗口（秒）
        <Input
          type="number"
          required
          min={1}
          step={1}
          value={window}
          onChange={(e) => setWindow(e.target.value)}
        />
      </label>
      <label className="grid gap-1 sm:col-span-2">
        修改原因
        <Input
          required
          maxLength={2000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />
        启用硬预算
      </label>
      <Button disabled={pending} type="submit" className="justify-self-start">
        保存预算
      </Button>
      {message && (
        <p role="status" className="sm:col-span-2">
          {message}
        </p>
      )}
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
  const [message, setMessage] = useState("");
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
      setMessage("预算已创建。");
      await saved();
    } catch (error) {
      setMessage(explain(error));
    } finally {
      setPending(false);
    }
  }
  return (
    <details className="bg-muted/30 rounded-lg p-4">
      <summary className="cursor-pointer font-medium">创建预算政策</summary>
      <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1">
          预算名称
          <Input
            required
            pattern="[a-z][a-z0-9_.:-]*"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
        </label>
        <label className="grid gap-1">
          计量单位
          <select
            className="bg-muted rounded-md p-2"
            value={metric}
            onChange={(e) =>
              setMetric(e.target.value as HotKeyAPI.BudgetMetric)
            }
          >
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
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label className="grid gap-1">
          范围
          <select
            className="bg-muted rounded-md p-2"
            value={scope}
            onChange={(e) =>
              setScope(e.target.value as HotKeyAPI.BudgetScopeKind)
            }
          >
            {(["global", "source", "connection", "job"] as const).map(
              (value) => (
                <option key={value}>{value}</option>
              ),
            )}
          </select>
        </label>
        {scope !== "global" && (
          <label className="grid gap-1">
            范围引用
            <Input
              required
              value={ref}
              onChange={(e) => setRef(e.target.value)}
            />
          </label>
        )}
        <label className="grid gap-1">
          创建预算上限
          <Input
            required
            type="number"
            min={1}
            step={1}
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
        </label>
        <label className="grid gap-1">
          创建预算窗口（秒）
          <Input
            required
            type="number"
            min={1}
            step={1}
            value={window}
            onChange={(e) => setWindow(e.target.value)}
          />
        </label>
        <label className="grid gap-1 sm:col-span-2">
          创建预算原因
          <Input
            required
            maxLength={2000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <Button type="submit" disabled={pending}>
          创建硬预算
        </Button>
        {message && <p role="status">{message}</p>}
      </form>
    </details>
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
  const [status, setStatus] = useState(row.status);
  const [note, setNote] = useState(row.note ?? "");
  const [reason, setReason] = useState("");
  const [banned, setBanned] = useState(row.banned);
  const [message, setMessage] = useState("");
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
      setMessage(explain(error));
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
      setMessage(explain(error));
    }
  }
  return (
    <article className="bg-muted/40 grid gap-3 rounded-lg p-4">
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
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1">
          处理状态
          <select
            aria-label="反馈处理状态"
            className="bg-background rounded-md p-2"
            value={status}
            onChange={(e) =>
              setStatus(e.target.value as HotKeyAPI.FeedbackView["status"])
            }
          >
            {["new", "reviewing", "resolved", "rejected", "deleted"].map(
              (value) => (
                <option key={value}>{value}</option>
              ),
            )}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={banned}
            onChange={(e) => setBanned(e.target.checked)}
          />
          封禁此匿名来源
        </label>
        <label className="grid gap-1 sm:col-span-2">
          处理备注
          <Textarea
            maxLength={2000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <label className="grid gap-1 sm:col-span-2">
          操作原因
          <Input
            required
            maxLength={2000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <Button disabled={pending} type="submit" className="justify-self-start">
          保存反馈处置
        </Button>
      </form>
      {status === "deleted" && (
        <p className="text-muted-foreground text-sm">
          保存后会清除正文、联系方式和截图。
        </p>
      )}
      {message && <p role="status">{message}</p>}
    </article>
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
  const [message, setMessage] = useState("");
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
      setMessage("词典新版本已保存。");
      await saved();
    } catch (error) {
      setMessage(
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
      <form onSubmit={submit} className="grid gap-3">
        <label className="grid gap-1">
          词典
          <select
            aria-label="词典类型"
            className="bg-muted rounded-md p-2"
            value={kind}
            onChange={(e) => {
              const value = e.target.value as HotKeyAPI.DictionaryInput["kind"];
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
            {["glossary", "entities", "categories"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
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
        <label className="grid gap-1">
          词典修改原因
          <Input
            aria-label="词典修改原因"
            required
            maxLength={2000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <Button disabled={pending} type="submit" className="justify-self-start">
          保存词典新版本
        </Button>
        {message && <p role="status">{message}</p>}
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
  const [outcome, setOutcome] =
    useState<HotKeyAPI.AuditResolutionInput["outcome"]>("not_delivered");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
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
      setMessage(explain(error));
    } finally {
      setPending(false);
    }
  }
  return (
    <form onSubmit={submit} className="mt-3 grid gap-3">
      <p className="text-sm">
        请先在目的地核对实际投递；核对结果不会自动再次发送。
      </p>
      <select
        aria-label="未知投递核对结果"
        className="bg-background rounded-md p-2"
        value={outcome}
        onChange={(e) =>
          setOutcome(
            e.target.value as HotKeyAPI.AuditResolutionInput["outcome"],
          )
        }
      >
        <option value="not_delivered">确认未送达</option>
        <option value="delivered">确认已送达</option>
      </select>
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
      {message && <p role="status">{message}</p>}
    </form>
  );
}

export function OperationsWorkspace() {
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
  const [message, setMessage] = useState("");
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
    setMessage("");
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
    setMessage("");
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
      if (current()) setMessage(explain(error));
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
      setMessage(`维护任务已受理：${job.job_id}。执行结果请刷新审计。`);
    } catch (error) {
      if (isCurrent(currentToken, captured)) setMessage(explain(error));
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
      if (isCurrent(currentToken, captured)) setMessage(explain(error));
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
      if (isCurrent(currentToken, captured)) setMessage(explain(error));
    }
  }
  return (
    <>
      <WorkspaceHeader current="operations" />
      <main className="mx-auto grid max-w-6xl gap-10 px-5 py-10 sm:px-8">
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
            className="grid max-w-lg gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              enter();
            }}
          >
            <label className="grid gap-2">
              运营 Token
              <Input
                aria-label="运营 Token"
                type="password"
                autoComplete="off"
                required
                maxLength={512}
                value={input}
                onChange={(e) => clearAccess(e.target.value)}
              />
            </label>
            <Button
              type="submit"
              disabled={pending}
              className="justify-self-start"
            >
              进入运营工作区
            </Button>
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
        {message && (
          <p role="status" className="text-sm break-words">
            {message}
          </p>
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
                <p className="text-muted-foreground">尚无真实进程心跳。</p>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {health.heartbeats.map((row) => (
                    <p
                      key={row.instance_id}
                      className="bg-muted/40 rounded-lg p-4"
                    >
                      {row.role} · {row.state}
                      <span className="text-muted-foreground block text-sm">
                        PID {row.pid} · {row.age_seconds} 秒前
                      </span>
                    </p>
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
                    <div
                      key={row.action}
                      className="bg-muted/40 rounded-lg p-4"
                    >
                      <p>
                        {labels[row.action] ?? row.action} ·{" "}
                        {row.enabled ? "已启用" : "已关闭"}
                      </p>
                      <p className="text-muted-foreground text-sm">
                        间隔 {row.interval_seconds} 秒 · 最近{" "}
                        {row.latest_audit?.status ?? "无执行记录"}
                      </p>
                    </div>
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
                    <section
                      key="source-health-report"
                      className="bg-muted/40 rounded-lg p-4"
                    >
                      <h3 className="font-semibold">最近来源周报</h3>
                      <p className="text-muted-foreground mt-2 text-sm whitespace-pre-wrap">
                        {report}
                      </p>
                      <p className="text-muted-foreground mt-2 text-xs">
                        {row.latest_audit?.after_state?.delivered === true
                          ? "已保存渠道成功回执"
                          : row.latest_audit?.status === "unknown"
                            ? "渠道结果未知，请核对后处理"
                            : "本地报告已保存；请在审计中查看投递状态"}
                      </p>
                    </section>
                  );
                })}
                {maintenance.findings.map((row) => (
                  <p key={row.key} className="bg-muted/40 rounded-lg p-4">
                    <strong>{row.title}</strong> · {row.severity}
                    <span className="text-muted-foreground block text-sm">
                      {row.detail}
                    </span>
                  </p>
                ))}
                <form onSubmit={run} className="grid gap-3 sm:grid-cols-2">
                  <label className="grid gap-1">
                    维护操作
                    <select
                      className="bg-muted rounded-md p-2"
                      value={action}
                      onChange={(e) =>
                        setAction(
                          e.target
                            .value as HotKeyAPI.MaintenanceInput["action"],
                        )
                      }
                    >
                      {Object.entries(labels).map(([key, value]) => (
                        <option value={key} key={key}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="grid gap-1">
                    维护原因
                    <Input
                      required
                      maxLength={2000}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </label>
                  {action === "verify_backup" && (
                    <label className="grid gap-1 sm:col-span-2">
                      备份编号
                      <Input
                        required
                        value={backupId}
                        onChange={(e) => setBackupId(e.target.value)}
                        placeholder="已完成备份的 UUID"
                      />
                    </label>
                  )}
                  <Button
                    type="submit"
                    disabled={pending}
                    className="justify-self-start"
                  >
                    受理维护任务
                  </Button>
                </form>
                <div className="grid gap-3">
                  {maintenance.backups.map((row) => (
                    <div key={row.id} className="bg-muted/40 rounded-lg p-4">
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
                    </div>
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
              {feedback.length === 0 && <p>暂无反馈。</p>}
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
                <article key={row.id} className="bg-muted/40 rounded-lg p-4">
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
                </article>
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
      </main>
    </>
  );
}

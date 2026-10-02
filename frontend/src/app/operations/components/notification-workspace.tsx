"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  listOperatorNotificationTargets,
  saveOperatorNotificationTarget,
  listOperatorNotificationDeliveries,
  resolveOperatorNotificationDelivery,
} from "@/api/yunyingweihu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiRequestError, type RequestOptions } from "@/request";

type Kind = "report" | "edition" | "selected" | "codex_reset";
const kinds: Record<Kind, string> = {
  report: "主题报告",
  edition: "日报 / 周刊 / 月刊",
  selected: "精选内容",
  codex_reset: "Codex 额度公告",
};
function explain(error: unknown) {
  return error instanceof ApiRequestError
    ? error.message
    : "通知操作失败，请保留输入后重试。";
}
function useOperation() {
  const identity = useRef<{ payload: string; id: string } | null>(null);
  return {
    id(input: unknown) {
      const payload = JSON.stringify(input);
      if (identity.current?.payload !== payload)
        identity.current = { payload, id: crypto.randomUUID() };
      return identity.current.id;
    },
    done() {
      identity.current = null;
    },
  };
}
function TargetEditor({
  row,
  options,
  saved,
}: {
  row?: HotKeyAPI.TargetView;
  options: RequestOptions;
  saved: () => Promise<void>;
}) {
  const [name, setName] = useState(row?.name ?? "");
  const [channel, setChannel] = useState<HotKeyAPI.NotificationChannel>(
    row?.channel ?? "email",
  );
  const [recipients, setRecipients] = useState(
    row?.recipients.join(", ") ?? "",
  );
  const [secretRef, setSecretRef] = useState(row?.secret_env ?? "");
  const [enabled, setEnabled] = useState(row?.enabled ?? false);
  const [subscriptions, setSubscriptions] = useState<Kind[]>(
    row?.subscriptions ?? ["report"],
  );
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const operation = useOperation();
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const input = {
        target_id: row?.id ?? null,
        expected_revision: row?.revision ?? 0,
        reason,
        target: {
          name,
          channel,
          enabled,
          subscriptions,
          recipients:
            channel === "email"
              ? recipients
                  .split(/[,;\n]/)
                  .map((value) => value.trim())
                  .filter(Boolean)
              : [],
          secret_env: channel === "feishu" && secretRef ? secretRef : null,
        },
      };
      await saveOperatorNotificationTarget(
        { ...input, operation_id: operation.id(input) },
        options,
      );
      operation.done();
      setMessage("通知目标已保存。");
      await saved();
    } catch (error) {
      setMessage(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      onSubmit={submit}
      className="bg-muted/30 grid gap-3 rounded-lg p-4 sm:grid-cols-2"
    >
      <label className="grid gap-1">
        目标名称
        <Input
          required
          maxLength={80}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label className="grid gap-1">
        通知渠道
        <select
          className="bg-muted rounded-md p-2"
          value={channel}
          onChange={(e) =>
            setChannel(e.target.value as HotKeyAPI.NotificationChannel)
          }
        >
          <option value="email">邮件 SMTP</option>
          <option value="feishu">飞书</option>
        </select>
      </label>
      {channel === "email" ? (
        <label className="grid gap-1 sm:col-span-2">
          收件人邮箱（逗号分隔，最多 20 个）
          <Input
            required
            value={recipients}
            onChange={(e) => setRecipients(e.target.value)}
          />
        </label>
      ) : (
        <label className="grid gap-1 sm:col-span-2">
          签名密钥环境变量名（可选，HOTKEY_ 前缀）
          <Input
            maxLength={128}
            value={secretRef}
            onChange={(e) => setSecretRef(e.target.value)}
          />
        </label>
      )}
      <fieldset className="grid gap-2 sm:col-span-2">
        <legend className="mb-2">订阅类别</legend>
        <div className="flex flex-wrap gap-4">
          {(Object.keys(kinds) as Kind[]).map((kind) => (
            <label key={kind} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={subscriptions.includes(kind)}
                onChange={(e) =>
                  setSubscriptions((old) =>
                    e.target.checked
                      ? [...old, kind]
                      : old.filter((value) => value !== kind),
                  )
                }
              />
              {kinds[kind]}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="grid gap-1 sm:col-span-2">
        通知配置原因
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
        启用此目标
      </label>
      <Button disabled={busy} type="submit">
        保存通知目标
      </Button>
      {row && (
        <p className="text-muted-foreground text-sm sm:col-span-2">
          修订 {row.revision} · 启用时间{" "}
          {row.enabled_at
            ? new Date(row.enabled_at).toLocaleString("zh-CN")
            : "未启用"}
        </p>
      )}
      {message && (
        <p role="status" className="sm:col-span-2">
          {message}
        </p>
      )}
    </form>
  );
}
function UnknownResolution({
  row,
  options,
  saved,
}: {
  row: HotKeyAPI.NotificationDeliveryView;
  options: RequestOptions;
  saved: () => Promise<void>;
}) {
  const [outcome, setOutcome] = useState<"delivered" | "not_delivered">(
    "not_delivered",
  );
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const operation = useOperation();
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const input = { expected_revision: row.revision, reason, outcome };
      await resolveOperatorNotificationDelivery(
        { delivery_id: row.id },
        { ...input, operation_id: operation.id(input) },
        options,
      );
      operation.done();
      await saved();
    } catch (error) {
      setMessage(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-2">
      <label className="grid gap-1">
        目的地核对结果
        <select
          className="bg-muted rounded-md p-2"
          value={outcome}
          onChange={(e) => setOutcome(e.target.value as typeof outcome)}
        >
          <option value="not_delivered">确认未送达</option>
          <option value="delivered">确认已送达</option>
        </select>
      </label>
      <label className="grid gap-1">
        核对依据
        <Input
          required
          maxLength={2000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <p className="text-muted-foreground text-sm sm:col-span-2">
        核对仅更新账本与原任务重试资格。确认未送达后，请到原任务显式重试；不会立即重发。
      </p>
      <Button type="submit" disabled={busy}>
        保存人工核对
      </Button>
      {message && <p role="status">{message}</p>}
    </form>
  );
}

export function NotificationWorkspace({ token }: { token: string }) {
  const [targets, setTargets] = useState<HotKeyAPI.TargetView[]>([]);
  const [selected, setSelected] = useState("");
  const [deliveries, setDeliveries] = useState<
    HotKeyAPI.NotificationDeliveryView[]
  >([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  const reload = useCallback(async () => {
    const current = ++sequence.current;
    const options = { headers: { "X-HotKey-Operator-Token": token } };
    try {
      const [rows, page] = await Promise.all([
        listOperatorNotificationTargets(options),
        listOperatorNotificationDeliveries({ limit: 50 }, options),
      ]);
      if (sequence.current !== current) return;
      setTargets(rows);
      setDeliveries(page.items);
      setCursor(page.next_cursor);
      setMessage("");
    } catch (error) {
      if (sequence.current === current) setMessage(explain(error));
    } finally {
      if (sequence.current === current) setBusy(false);
    }
  }, [token]);
  useEffect(() => {
    const pending = sequence;
    const current = ++pending.current;
    const options = { headers: { "X-HotKey-Operator-Token": token } };
    Promise.all([
      listOperatorNotificationTargets(options),
      listOperatorNotificationDeliveries({ limit: 50 }, options),
    ])
      .then(([rows, page]) => {
        if (pending.current !== current) return;
        setTargets(rows);
        setDeliveries(page.items);
        setCursor(page.next_cursor);
        setMessage("");
      })
      .catch((error) => {
        if (pending.current === current) setMessage(explain(error));
      });
    return () => {
      pending.current++;
    };
  }, [token]);
  const options = { headers: { "X-HotKey-Operator-Token": token } };
  async function more() {
    if (!cursor) return;
    setBusy(true);
    try {
      const page = await listOperatorNotificationDeliveries(
        { cursor, limit: 50 },
        options,
      );
      setDeliveries((old) => [...old, ...page.items]);
      setCursor(page.next_cursor);
    } catch (error) {
      setMessage(explain(error));
    } finally {
      setBusy(false);
    }
  }
  const target = targets.find((row) => row.id === selected);
  return (
    <section className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">通知订阅与投递账本</h2>
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => void reload()}
        >
          刷新通知状态
        </Button>
      </div>
      <p className="text-muted-foreground text-sm">
        SMTP
        和飞书凭据在服务端环境中配置，新目标默认停用。主题报告还需在关注主题中绑定目标名称；全站刊物由刊物订阅处理。保存启用配置后从新的启用时间开始扫描，首个扫描窗口可能等待
        5 分钟。
      </p>
      <label className="grid gap-1">
        选择通知目标
        <select
          className="bg-muted rounded-md p-2"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">创建新目标</option>
          {targets.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name} · {row.enabled ? "已启用" : "已停用"}
            </option>
          ))}
        </select>
      </label>
      <TargetEditor
        key={target ? `${target.id}:${target.revision}` : "new"}
        row={target}
        options={options}
        saved={reload}
      />
      {message && <p role="status">{message}</p>}
      {deliveries.length === 0 && (
        <p className="text-muted-foreground">暂无投递记录。</p>
      )}
      {deliveries.map((row) => (
        <article
          key={`${row.id}:${row.revision}`}
          className="bg-muted/30 rounded-lg p-4"
        >
          <p className="break-all">
            {kinds[row.subject_kind]} ·{" "}
            {targets.find((value) => value.id === row.target_id)?.name ??
              row.target_id}{" "}
            · {row.status === "succeeded" ? "渠道受理 / 人工确认" : row.status}
          </p>
          <p className="text-muted-foreground mt-1 text-sm break-all">
            主体 {row.subject_id} · 版本 {row.subject_revision} · 尝试{" "}
            {row.attempt_count}/3 ·{" "}
            {new Date(row.updated_at).toLocaleString("zh-CN")}
          </p>
          {row.last_error_code && (
            <p className="mt-2 text-sm">{row.last_error_code}</p>
          )}
          {Object.keys(row.provider_receipt).length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-sm">
                渠道实际回执（SMTP 受理不表示已到达收件箱）
              </summary>
              <pre className="mt-2 overflow-auto text-xs">
                {JSON.stringify(row.provider_receipt, null, 2)}
              </pre>
            </details>
          )}
          {row.status === "unknown" && (
            <UnknownResolution row={row} options={options} saved={reload} />
          )}
        </article>
      ))}
      {cursor && (
        <Button variant="secondary" disabled={busy} onClick={() => void more()}>
          加载更多投递记录
        </Button>
      )}
    </section>
  );
}

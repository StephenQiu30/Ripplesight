"use client";
import { Item, ItemContent, ItemDescription } from "@/components/ui/item";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import { toast } from "sonner";
import { ChevronDownIcon } from "lucide-react";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { Checkbox } from "@/components/ui/checkbox";
import {
  SelectLabel,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from "@/components/ui/select";
import {
  FieldGroup,
  FieldLabel,
  Field,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { useId, useCallback, useEffect, useRef, useState } from "react";
import {
  listOperatorNotificationTargets,
  saveOperatorNotificationTarget,
  listOperatorNotificationDeliveries,
  resolveOperatorNotificationDelivery,
} from "@/api/yunyingweihu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiRequestError, type RequestOptions } from "@/request";

type Kind = HotKeyAPI.NotificationSubjectKind;
const kinds: Record<Kind, string> = {
  report: "主题报告",
  edition: "日报 / 周刊 / 月刊",
  selected: "精选内容",
  codex_reset: "Codex 额度公告",
  alert: "突发告警",
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
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const fieldId = useId();

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
      if (mounted.current) toast.success("通知目标已保存。");
      await saved();
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (mounted.current) toast.error(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit}>
      <Item variant="muted" asChild>
        <FieldGroup className="grid gap-3 p-4 sm:grid-cols-2">
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-notification-workspace-field-1`}>
              目标名称
            </FieldLabel>
            <Input
              required
              maxLength={80}
              value={name}
              onChange={(e) => setName(e.target.value)}
              id={`${fieldId}-notification-workspace-field-1`}
            />
          </Field>
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-notification-workspace-field-2`}>
              通知渠道
            </FieldLabel>
            <Select
              value={channel}
              onValueChange={(selectedValue) =>
                setChannel(selectedValue as HotKeyAPI.NotificationChannel)
              }
            >
              <SelectTrigger
                id={`${fieldId}-notification-workspace-field-2`}
                className="w-full min-w-0"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper">
                <SelectGroup>
                  <SelectLabel className="sr-only">通知渠道</SelectLabel>
                  <SelectItem value="email" className="whitespace-normal">
                    邮件 SMTP
                  </SelectItem>
                  <SelectItem value="feishu" className="whitespace-normal">
                    飞书
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </Field>
          {channel === "email" ? (
            <Field className="min-w-0 sm:col-span-2">
              <FieldLabel htmlFor={`${fieldId}-notification-workspace-field-3`}>
                收件人邮箱（逗号分隔，最多 20 个）
              </FieldLabel>
              <Input
                required
                value={recipients}
                onChange={(e) => setRecipients(e.target.value)}
                id={`${fieldId}-notification-workspace-field-3`}
              />
            </Field>
          ) : (
            <Field className="min-w-0 sm:col-span-2">
              <FieldLabel htmlFor={`${fieldId}-notification-workspace-field-4`}>
                签名密钥环境变量名（可选，HOTKEY_ 前缀）
              </FieldLabel>
              <Input
                maxLength={128}
                value={secretRef}
                onChange={(e) => setSecretRef(e.target.value)}
                id={`${fieldId}-notification-workspace-field-4`}
              />
            </Field>
          )}
          <FieldSet className="grid gap-2 sm:col-span-2">
            <FieldLegend className="mb-2">订阅类别</FieldLegend>
            <div className="flex flex-wrap gap-4">
              {(Object.keys(kinds) as Kind[]).map((kind) => (
                <Field key={kind} orientation="horizontal" className="w-auto">
                  <Checkbox
                    checked={subscriptions.includes(kind)}
                    onCheckedChange={(checked) =>
                      setSubscriptions((old) =>
                        checked === true
                          ? [...old, kind]
                          : old.filter((value) => value !== kind),
                      )
                    }
                    id={`${fieldId}-notification-workspace-field-5-${kind}`}
                  />
                  <FieldLabel
                    htmlFor={`${fieldId}-notification-workspace-field-5-${kind}`}
                  >
                    {kinds[kind]}
                  </FieldLabel>
                </Field>
              ))}
            </div>
          </FieldSet>
          <Field className="min-w-0 sm:col-span-2">
            <FieldLabel htmlFor={`${fieldId}-notification-workspace-field-6`}>
              通知配置原因
            </FieldLabel>
            <Input
              required
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              id={`${fieldId}-notification-workspace-field-6`}
            />
          </Field>
          <Field orientation="horizontal" className="w-auto">
            <Checkbox
              checked={enabled}
              onCheckedChange={(checked) => setEnabled(checked === true)}
              id={`${fieldId}-notification-workspace-field-7`}
            />
            <FieldLabel htmlFor={`${fieldId}-notification-workspace-field-7`}>
              启用此目标
            </FieldLabel>
          </Field>
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
        </FieldGroup>
      </Item>
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
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const fieldId = useId();

  const [outcome, setOutcome] = useState<"delivered" | "not_delivered">(
    "not_delivered",
  );
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

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
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (mounted.current) toast.error(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit}>
      <FieldGroup className="mt-3 grid gap-3 sm:grid-cols-2">
        <Field className="min-w-0">
          <FieldLabel htmlFor={`${fieldId}-notification-workspace-field-8`}>
            目的地核对结果
          </FieldLabel>
          <Select
            value={outcome}
            onValueChange={(selectedValue) =>
              setOutcome(selectedValue as typeof outcome)
            }
          >
            <SelectTrigger
              id={`${fieldId}-notification-workspace-field-8`}
              className="w-full min-w-0"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent position="popper">
              <SelectGroup>
                <SelectLabel className="sr-only">目的地核对结果</SelectLabel>
                <SelectItem value="not_delivered" className="whitespace-normal">
                  确认未送达
                </SelectItem>
                <SelectItem value="delivered" className="whitespace-normal">
                  确认已送达
                </SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
        <Field className="min-w-0">
          <FieldLabel htmlFor={`${fieldId}-notification-workspace-field-9`}>
            核对依据
          </FieldLabel>
          <Input
            required
            maxLength={2000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            id={`${fieldId}-notification-workspace-field-9`}
          />
        </Field>
        <p className="text-muted-foreground text-sm sm:col-span-2">
          核对仅更新账本与原任务重试资格。确认未送达后，请到原任务显式重试；不会立即重发。
        </p>
        <Button type="submit" disabled={busy}>
          保存人工核对
        </Button>
      </FieldGroup>
    </form>
  );
}

export function NotificationWorkspace({ token }: { token: string }) {
  const fieldId = useId();

  const [targets, setTargets] = useState<HotKeyAPI.TargetView[]>([]);
  const [selected, setSelected] = useState("");
  const [deliveries, setDeliveries] = useState<
    HotKeyAPI.NotificationDeliveryView[]
  >([]);
  const [cursor, setCursor] = useState<string | null>(null);

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
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (sequence.current === current) toast.error(explain(error));
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
      })
      .catch((error) => {
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (pending.current === current) toast.error(explain(error));
      });
    return () => {
      pending.current++;
    };
  }, [token]);
  const options = { headers: { "X-HotKey-Operator-Token": token } };
  async function more() {
    if (!cursor) return;
    const current = sequence.current;
    setBusy(true);
    try {
      const page = await listOperatorNotificationDeliveries(
        { cursor, limit: 50 },
        options,
      );
      if (sequence.current !== current) return;
      setDeliveries((old) => [...old, ...page.items]);
      setCursor(page.next_cursor);
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (sequence.current === current) toast.error(explain(error));
    } finally {
      if (sequence.current === current) setBusy(false);
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
      <Field className="min-w-0">
        <FieldLabel htmlFor={`${fieldId}-notification-workspace-field-10`}>
          选择通知目标
        </FieldLabel>
        <Select
          value={selected}
          onValueChange={(selectedValue) =>
            setSelected(selectedValue === "__none__" ? "" : selectedValue)
          }
        >
          <SelectTrigger
            id={`${fieldId}-notification-workspace-field-10`}
            className="w-full min-w-0"
          >
            <SelectValue placeholder="创建新目标" />
          </SelectTrigger>
          <SelectContent position="popper">
            <SelectGroup>
              <SelectLabel className="sr-only">选择通知目标</SelectLabel>
              <SelectItem value="__none__" className="whitespace-normal">
                创建新目标
              </SelectItem>
              {targets.map((row) => (
                <SelectItem
                  key={row.id}
                  value={row.id}
                  className="whitespace-normal"
                >
                  {row.name} · {row.enabled ? "已启用" : "已停用"}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      </Field>
      <TargetEditor
        key={target ? `${target.id}:${target.revision}` : "new"}
        row={target}
        options={options}
        saved={reload}
      />
      {deliveries.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyDescription>暂无投递记录。</EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}
      {deliveries.map((row) => (
        <Item variant="muted" key={`${row.id}:${row.revision}`} asChild>
          <article className="p-4">
            <ItemContent className="min-w-0 gap-3">
              <p className="break-all">
                {kinds[row.subject_kind]} ·{" "}
                {targets.find((value) => value.id === row.target_id)?.name ??
                  row.target_id}{" "}
                ·{" "}
                {row.status === "succeeded"
                  ? "渠道受理 / 人工确认"
                  : row.status}
              </p>
              <ItemDescription className="mt-1 line-clamp-none break-all">
                主体 {row.subject_id} · 版本 {row.subject_revision} · 尝试{" "}
                {row.attempt_count}/3 ·{" "}
                {new Date(row.updated_at).toLocaleString("zh-CN")}
              </ItemDescription>
              {row.last_error_code && (
                <p className="mt-2 text-sm">{row.last_error_code}</p>
              )}
              {Object.keys(row.provider_receipt).length > 0 && (
                <Collapsible className="mt-3">
                  <CollapsibleTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
                    >
                      <span className="min-w-0 text-left">
                        渠道实际回执（SMTP 受理不表示已到达收件箱）
                      </span>
                      <ChevronDownIcon
                        aria-hidden="true"
                        data-icon="inline-end"
                        className="group-data-[state=open]:rotate-180"
                      />
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent
                    forceMount
                    className="data-[state=closed]:hidden"
                  >
                    <pre className="mt-2 overflow-auto text-xs">
                      {JSON.stringify(row.provider_receipt, null, 2)}
                    </pre>
                  </CollapsibleContent>
                </Collapsible>
              )}
              {row.status === "unknown" && (
                <UnknownResolution row={row} options={options} saved={reload} />
              )}
            </ItemContent>
          </article>
        </Item>
      ))}
      {cursor && (
        <Button variant="secondary" disabled={busy} onClick={() => void more()}>
          加载更多投递记录
        </Button>
      )}
    </section>
  );
}

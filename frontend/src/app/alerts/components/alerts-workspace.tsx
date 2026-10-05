"use client";
import * as UI from "@/components/ui/content";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
} from "react";
import Link from "next/link";
import {
  createAlert,
  listAlerts,
  listAlertTargets,
  listAlertHistory,
  updateAlert,
} from "@/api/gerentufagaojing";
import { listMonitorTopics } from "@/api/jiankongzhuti";
import { listEvents } from "@/api/shijian";
import { ApiRequestError } from "@/request";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Item, ItemContent } from "@/components/ui/item";
import { Spinner } from "@/components/ui/spinner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Sources = {
  topics: HotKeyAPI.MonitorTopicView[];
  targets: HotKeyAPI.AlertTargetView[];
  events: HotKeyAPI.EventReadView[];
};

async function readChoices<T>(
  read: (
    cursor: string | null,
  ) => Promise<{ items: T[]; next_cursor?: string | null }>,
): Promise<T[]> {
  const items: T[] = [];
  const seen = new Set<string>();
  let cursor: string | null = null;
  for (let page = 0; page < 100; page += 1) {
    const result = await read(cursor);
    items.push(...result.items);
    cursor = result.next_cursor ?? null;
    if (!cursor) return items;
    if (seen.has(cursor)) throw new Error("invalid_choice_cursor");
    seen.add(cursor);
  }
  throw new Error("choice_page_limit");
}

function failure(error: unknown) {
  return error instanceof ApiRequestError
    ? error.message
    : "告警操作失败，请保留输入后重试。";
}

function reasonLabel(reason: string | null) {
  if (!reason) return "";
  const labels: Record<string, string> = {
    notification_disabled: "通知发送尚未启用。",
    alert_target_unavailable: "通知目标当前不可用。",
    alert_target_stale: "通知目标的版本、订阅或验证条件尚未满足。",
    alert_target_unverified: "当前通知目标尚无已确认的送达回执。",
    alert_topic_stale: "关注规则已变更，请重新保存告警。",
    alert_delivery_unknown: "上次送达结果未知，需人工核查；不会自动重发。",
    alert_cooldown: "规则处于冷却期。",
    alert_delivery_not_admitted: "投递准入条件尚未满足。",
    alert_input_deleted: "固定输入已删除，该结果已撤回。",
    notifications_disabled: "通知发送尚未启用。",
    target_unavailable: "通知目标未就绪。",
    target_not_verified: "通知目标尚未验证。",
    target_revision_changed: "通知目标已变更，请重新选择。",
    topic_version_changed: "关注规则已变更，请重新保存告警。",
    insufficient_inputs: "缺少可用的固定输入，无法判定。",
    source_withdrawn: "输入许可已失效。",
  };
  return labels[reason] ?? "条件尚未满足，请核对关注规则、有效输入与通知目标。";
}

function Choice({
  id,
  value,
  onChange,
  children,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <Select value={value || undefined} onValueChange={onChange}>
      <SelectTrigger id={id} className="w-full min-w-0">
        <SelectValue placeholder="请选择" />
      </SelectTrigger>
      <SelectContent position="popper">{children}</SelectContent>
    </Select>
  );
}

function RuleEditor({
  row,
  sources,
  saved,
  cancel,
}: {
  row?: HotKeyAPI.AlertRuleView;
  sources: Sources;
  saved: (rule: HotKeyAPI.AlertRuleView) => void;
  cancel: () => void;
}) {
  const id = useId();
  const mounted = useRef(true);
  const busyRef = useRef(false);
  const operation = useRef<{ payload: string; id: string } | null>(null);
  const [name, setName] = useState(row?.name ?? "");
  const [topicId, setTopicId] = useState(row?.topic_id ?? "");
  const [metric, setMetric] = useState<HotKeyAPI.AlertRuleInput["metric"]>(
    row?.metric ?? "negative_count",
  );
  const [eventId, setEventId] = useState(row?.event_id ?? "");
  const [threshold, setThreshold] = useState(String(row?.threshold ?? 10));
  const [cooldown, setCooldown] = useState(
    String((row?.cooldown_seconds ?? 3600) / 60),
  );
  const [targetId, setTargetId] = useState(row?.target_id ?? "");
  const [enabled, setEnabled] = useState(row?.enabled ?? false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const topic = sources.topics.find((item) => item.id === topicId);
  const target = sources.targets.find((item) => item.id === targetId);
  const events = sources.events.filter(
    (item) => item.topic_id === topicId && item.status === "active",
  );
  const canEnable = Boolean(
    topic &&
    target?.eligible &&
    (metric !== "heat_increment" || events.some((item) => item.id === eventId)),
  );

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busyRef.current) return;
    const value = Number(threshold);
    const seconds = Number(cooldown) * 60;
    if (
      !topic ||
      !target ||
      !name.trim() ||
      !Number.isFinite(value) ||
      value <= 0 ||
      value > 1_000_000_000 ||
      (metric === "negative_count" && !Number.isInteger(value)) ||
      !Number.isInteger(seconds) ||
      seconds < 300 ||
      seconds > 86400 ||
      (metric === "heat_increment" &&
        !events.some((item) => item.id === eventId))
    ) {
      setError(
        "请填写名称、关注、有效阈值、5—1440 分钟冷却时间和通知目标；热度规则还需选择该关注下的事件。",
      );
      return;
    }
    if (enabled && !canEnable) {
      setError("通知目标尚未就绪，请先关闭规则再保存。");
      return;
    }
    const input = {
      expected_revision: row?.revision ?? 0,
      name: name.trim(),
      topic_id: topic.id,
      topic_rule_version: topic.current_version,
      event_id: metric === "heat_increment" ? eventId : null,
      metric,
      threshold: value,
      cooldown_seconds: seconds,
      target_id: target.id,
      target_revision: target.revision,
      enabled,
    };
    const payload = JSON.stringify(input);
    if (operation.current?.payload !== payload)
      operation.current = { payload, id: crypto.randomUUID() };
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      const body = { ...input, operation_id: operation.current.id };
      const result = row
        ? await updateAlert({ rule_id: row.id }, body)
        : await createAlert(body);
      operation.current = null;
      if (mounted.current) saved(result);
    } catch (caught) {
      if (mounted.current) setError(failure(caught));
    } finally {
      busyRef.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <UI.Form
      onSubmit={submit}
      className="rounded-xl border p-5"
      aria-label={row ? "编辑告警规则" : "新建告警规则"}
    >
      <UI.Heading level={2} className="mb-5 text-lg font-medium">
        {row ? "编辑告警规则" : "新建告警规则"}
      </UI.Heading>
      <FieldGroup className="grid gap-5 sm:grid-cols-2">
        <Field>
          <FieldLabel htmlFor={`${id}-name`}>规则名称</FieldLabel>
          <Input
            id={`${id}-name`}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={80}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor={`${id}-topic`}>关注方向</FieldLabel>
          <Choice
            id={`${id}-topic`}
            value={topicId}
            onChange={(value) => {
              setTopicId(value);
              setEventId("");
            }}
          >
            {sources.topics.map((item) => (
              <SelectItem key={item.id} value={item.id}>
                {item.name}
              </SelectItem>
            ))}
          </Choice>
        </Field>
        <Field>
          <FieldLabel htmlFor={`${id}-metric`}>判断指标</FieldLabel>
          <Choice
            id={`${id}-metric`}
            value={metric}
            onChange={(value) =>
              setMetric(value as HotKeyAPI.AlertRuleInput["metric"])
            }
          >
            <SelectItem value="negative_count">
              有效情感计数（已采集材料）
            </SelectItem>
            <SelectItem value="heat_increment">
              同公式 1 小时可比热度增量
            </SelectItem>
          </Choice>
          <FieldDescription>
            负面计数使用最近一小时首次取得的材料中有效的负面分析；未分析材料不会算作零负面。
          </FieldDescription>
        </Field>
        {metric === "heat_increment" && (
          <Field>
            <FieldLabel htmlFor={`${id}-event`}>关注下的事件</FieldLabel>
            <Choice id={`${id}-event`} value={eventId} onChange={setEventId}>
              {events.map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.title ?? "未命名事件"}
                </SelectItem>
              ))}
            </Choice>
            <FieldDescription>
              缺少同公式可比快照时，结果为无法判定。
            </FieldDescription>
          </Field>
        )}
        <Field>
          <FieldLabel htmlFor={`${id}-threshold`}>触发阈值</FieldLabel>
          <Input
            id={`${id}-threshold`}
            type="number"
            min={metric === "negative_count" ? 1 : 0.000001}
            max={1_000_000_000}
            step={metric === "negative_count" ? 1 : "any"}
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            required
          />
        </Field>
        <Field>
          <FieldLabel htmlFor={`${id}-cooldown`}>冷却时间（分钟）</FieldLabel>
          <Input
            id={`${id}-cooldown`}
            type="number"
            min={5}
            max={1440}
            step={1}
            value={cooldown}
            onChange={(e) => setCooldown(e.target.value)}
            required
          />
        </Field>
        <Field>
          <FieldLabel htmlFor={`${id}-target`}>通知目标</FieldLabel>
          <Choice id={`${id}-target`} value={targetId} onChange={setTargetId}>
            {sources.targets.map((item) => (
              <SelectItem key={item.id} value={item.id}>
                {item.name}
                {item.eligible ? "" : "（未就绪）"}
              </SelectItem>
            ))}
          </Choice>
          {target && !target.eligible && (
            <FieldDescription>{reasonLabel(target.reason)}</FieldDescription>
          )}
        </Field>
        <Field className="sm:col-span-2">
          <UI.Content className="flex items-center gap-3">
            <Checkbox
              id={`${id}-enabled`}
              checked={enabled}
              disabled={!canEnable && !enabled}
              onCheckedChange={(value) => setEnabled(value === true)}
            />
            <FieldLabel htmlFor={`${id}-enabled`}>启用规则</FieldLabel>
          </UI.Content>
          <FieldDescription>
            规则默认关闭；保存不会发送测试通知。通知发送及目标验证需要各自就绪。
          </FieldDescription>
        </Field>
      </FieldGroup>
      {error && (
        <Alert variant="destructive" className="mt-5">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <UI.Content className="mt-5 flex gap-3">
        <Button
          type="submit"
          disabled={busy || !sources.topics.length || !sources.targets.length}
        >
          {busy ? "正在保存…" : "保存规则"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={cancel}
          disabled={busy}
        >
          取消
        </Button>
      </UI.Content>
    </UI.Form>
  );
}

function History({ ruleId }: { ruleId: string }) {
  const [rows, setRows] = useState<HotKeyAPI.AlertEvaluationView[] | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
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
        if (generation.current === request) setError(failure(caught));
      });
  }, [ruleId]);
  useEffect(() => {
    void load();
    return () => {
      generation.current += 1;
    };
  }, [load]);
  const labels: Record<HotKeyAPI.AlertEvaluationView["status"], string> = {
    blocked: "条件未满足",
    unknown: "无法判定",
    below_threshold: "未达阈值",
    cooldown: "冷却中",
    triggered: "已触发",
    withdrawn: "输入已撤回",
  };
  return (
    <UI.Content className="mt-4 space-y-3" aria-label="告警评估历史">
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>
            {error}
            <Button
              variant="outline"
              onClick={() => {
                void load();
              }}
            >
              重试历史
            </Button>
          </AlertDescription>
        </Alert>
      ) : !rows ? (
        <Item role="status">
          <Spinner />
          <ItemContent>正在读取评估历史…</ItemContent>
        </Item>
      ) : !rows.length ? (
        <UI.Text className="text-muted-foreground text-sm">
          尚无评估记录。启用后每五分钟评估一次；条件不足会保留原因。
        </UI.Text>
      ) : (
        rows.map((item) => (
          <Item key={item.id} variant="outline">
            <ItemContent>
              <UI.Text>
                {labels[item.status]} ·{" "}
                {new Date(item.window_end).toLocaleString("zh-CN")}
              </UI.Text>
              <UI.Text className="text-muted-foreground mt-1">
                指标：{item.value === null ? "未知" : item.value} · 规则版本{" "}
                {item.rule_version}
              </UI.Text>
              {item.reason && (
                <UI.Text className="mt-1">{reasonLabel(item.reason)}</UI.Text>
              )}
              {item.cooldown_until && (
                <UI.Text className="mt-1">
                  冷却至 {new Date(item.cooldown_until).toLocaleString("zh-CN")}
                </UI.Text>
              )}
            </ItemContent>
          </Item>
        ))
      )}
    </UI.Content>
  );
}

export function AlertsWorkspace() {
  const [data, setData] = useState<
    (Sources & { rules: HotKeyAPI.AlertRuleView[] }) | null
  >(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<
    HotKeyAPI.AlertRuleView | "new" | null
  >(null);
  const [historyId, setHistoryId] = useState<string | null>(null);
  const generation = useRef(0);
  const load = useCallback(() => {
    const request = ++generation.current;
    return Promise.all([
      listAlerts(),
      listAlertTargets(),
      readChoices((cursor) => listMonitorTopics({ limit: 50, cursor })),
      readChoices((cursor) => listEvents({ limit: 100, cursor })),
    ])
      .then(([rules, targets, topics, events]) => {
        if (generation.current === request) {
          setData({
            rules,
            targets,
            topics,
            events,
          });
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (generation.current === request) setError(failure(caught));
      });
  }, []);
  useEffect(() => {
    void load();
    return () => {
      generation.current += 1;
    };
  }, [load]);
  return (
    <UI.Content className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <UI.Content>
        <UI.Heading level={1} className="text-3xl font-medium tracking-tight">
          突发告警
        </UI.Heading>
        <UI.Text className="text-muted-foreground mt-3 leading-7">
          使用已取得且许可有效的材料评估规则，查看触发与冷却记录。无法判定和送达未知分别记录；未知送达不会自动重发。
        </UI.Text>
      </UI.Content>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>
            {error}
            <Button
              variant="outline"
              onClick={() => {
                void load();
              }}
            >
              重试加载
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {!data ? (
        !error && (
          <Item role="status">
            <Spinner />
            <ItemContent>正在读取告警配置…</ItemContent>
          </Item>
        )
      ) : (
        <>
          {!data.topics.length && (
            <UI.Text>
              先
              <Link href="/monitors/new" className="underline">
                创建关注方向
              </Link>
              ，再配置告警规则。
            </UI.Text>
          )}
          {!data.targets.length && (
            <UI.Text>
              尚无通知目标。请在
              <Link href="/operations" className="underline">
                运营与通知
              </Link>
              中配置获准的目标，完成验证后再启用规则。
            </UI.Text>
          )}
          {editing !== null ? (
            <RuleEditor
              key={editing === "new" ? "new" : editing.id}
              row={editing === "new" ? undefined : editing}
              sources={data}
              cancel={() => setEditing(null)}
              saved={(rule) => {
                setData((previous) =>
                  previous
                    ? {
                        ...previous,
                        rules: [
                          rule,
                          ...previous.rules.filter(
                            (item) => item.id !== rule.id,
                          ),
                        ],
                      }
                    : previous,
                );
                setEditing(null);
              }}
            />
          ) : (
            <Button
              className="self-start"
              onClick={() => setEditing("new")}
              disabled={!data.topics.length || !data.targets.length}
            >
              新建规则
            </Button>
          )}
          {!data.rules.length ? (
            <UI.Text className="text-muted-foreground">
              尚未配置告警规则，当前不会发送告警。
            </UI.Text>
          ) : (
            data.rules.map((rule) => (
              <UI.Content as="section" key={rule.id} className="min-w-0">
                <UI.Content className="flex flex-wrap items-start justify-between gap-4">
                  <UI.Content className="min-w-0">
                    <UI.Heading
                      level={2}
                      className="text-lg font-medium break-words"
                    >
                      {rule.name}
                    </UI.Heading>
                    <UI.Text className="text-muted-foreground mt-2 text-sm">
                      {rule.enabled ? "已启用" : "已关闭"} ·{" "}
                      {rule.metric === "negative_count"
                        ? "有效负面情感计数"
                        : "同公式热度增量"}{" "}
                      ≥ {rule.threshold} · 冷却 {rule.cooldown_seconds / 60}{" "}
                      分钟
                    </UI.Text>
                    {rule.readiness === "blocked" && (
                      <UI.Text className="mt-2 text-sm">
                        {reasonLabel(rule.reason)}
                      </UI.Text>
                    )}
                  </UI.Content>
                  <UI.Content className="flex gap-2">
                    <Button variant="outline" onClick={() => setEditing(rule)}>
                      编辑
                    </Button>
                    <Button
                      variant="outline"
                      aria-expanded={historyId === rule.id}
                      onClick={() =>
                        setHistoryId((current) =>
                          current === rule.id ? null : rule.id,
                        )
                      }
                    >
                      评估历史
                    </Button>
                  </UI.Content>
                </UI.Content>
                {historyId === rule.id && <History ruleId={rule.id} />}
              </UI.Content>
            ))
          )}
        </>
      )}
    </UI.Content>
  );
}

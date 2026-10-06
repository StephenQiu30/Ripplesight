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
  updateAlert,
} from "@/api/gerentufagaojing";
import { listMonitorTopics } from "@/api/jiankongzhuti";
import { listEvents } from "@/api/shijian";
import { toast } from "sonner";
import { ApiRequestError } from "@/request";
import { PageState } from "@/components/system/page-state";
import { AlertHistory } from "@/components/monitors/alert-history";
import { AlertRuleSummary } from "@/components/monitors/alert-rule-summary";
import { alertReasonLabel } from "@/components/monitors/alert-presenters";
import {
  readMonitorFailure,
  type MonitorFailure,
} from "@/components/monitors/monitor-presenters";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ItemGroup } from "@/components/ui/item";
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

function Choice({
  id,
  value,
  onChange,
  children,
  invalid = false,
}: {
  invalid?: boolean;
  id: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <Select value={value || undefined} onValueChange={onChange}>
      <SelectTrigger id={id} className="w-full min-w-0" aria-invalid={invalid}>
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
  const [invalidFields, setInvalidFields] = useState<string[]>([]);
  const formRef = useRef<HTMLFormElement>(null);
  useEffect(() => {
    formRef.current?.querySelector<HTMLElement>("[aria-invalid=true]")?.focus();
  }, [invalidFields]);
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
    const invalid: string[] = [];
    if (!name.trim() || name.trim().length > 80) invalid.push("name");
    if (!topic) invalid.push("topic_id");
    if (
      !Number.isFinite(value) ||
      value <= 0 ||
      value > 1_000_000_000 ||
      (metric === "heat_increment" && value < 0.000001) ||
      (metric === "negative_count" && !Number.isInteger(value))
    )
      invalid.push("threshold");
    if (
      !Number.isInteger(Number(cooldown)) ||
      !Number.isInteger(seconds) ||
      seconds < 300 ||
      seconds > 86400
    )
      invalid.push("cooldown_seconds");
    if (!target) invalid.push("target_id");
    if (
      metric === "heat_increment" &&
      !events.some((item) => item.id === eventId)
    )
      invalid.push("event_id");
    if (invalid.length || !topic || !target) {
      setInvalidFields(invalid);
      toast.error(
        "请填写名称、关注、有效阈值、5—1440 分钟冷却时间和通知目标；热度规则还需选择该关注下的事件。",
      );
      return;
    }
    if (enabled && !canEnable) {
      setInvalidFields(["enabled"]);
      toast.error("通知目标尚未就绪，请先关闭规则再保存。");
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
    setInvalidFields([]);
    try {
      const body = { ...input, operation_id: operation.current.id };
      const result = row
        ? await updateAlert({ rule_id: row.id }, body)
        : await createAlert(body);
      operation.current = null;
      if (mounted.current) {
        toast.success("告警规则已保存。");
        saved(result);
      }
    } catch (caught) {
      if (
        !mounted.current ||
        (caught instanceof ApiRequestError && caught.kind === "cancelled")
      )
        return;
      setInvalidFields(
        caught instanceof ApiRequestError && caught.status === 422
          ? (caught.details ?? []).flatMap((detail) =>
              typeof detail.location[1] === "string"
                ? [detail.location[1]]
                : [],
            )
          : [],
      );
      toast.error(failure(caught));
    } finally {
      busyRef.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <UI.Form
      ref={formRef}
      onSubmit={submit}
      noValidate
      className="flex min-w-0 flex-col gap-5"
      aria-label={row ? "编辑告警规则" : "新建告警规则"}
    >
      <UI.Heading level={2}>{row ? "编辑告警规则" : "新建告警规则"}</UI.Heading>
      <FieldGroup className="grid gap-5 sm:grid-cols-2">
        <Field>
          <FieldLabel htmlFor={`${id}-name`}>规则名称</FieldLabel>
          <Input
            id={`${id}-name`}
            aria-invalid={invalidFields.includes("name")}
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
            invalid={invalidFields.includes("topic_id")}
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
            invalid={invalidFields.includes("metric")}
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
            <Choice
              id={`${id}-event`}
              invalid={invalidFields.includes("event_id")}
              value={eventId}
              onChange={setEventId}
            >
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
            aria-invalid={invalidFields.includes("threshold")}
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
            aria-invalid={invalidFields.includes("cooldown_seconds")}
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
          <Choice
            id={`${id}-target`}
            invalid={invalidFields.includes("target_id")}
            value={targetId}
            onChange={setTargetId}
          >
            {sources.targets.map((item) => (
              <SelectItem key={item.id} value={item.id}>
                {item.name}
                {item.eligible ? "" : "（未就绪）"}
              </SelectItem>
            ))}
          </Choice>
          {target && !target.eligible && (
            <FieldDescription>
              {alertReasonLabel(target.reason)}
            </FieldDescription>
          )}
        </Field>
        <Field className="sm:col-span-2">
          <UI.Content className="flex items-center gap-3">
            <Switch
              aria-invalid={invalidFields.includes("enabled")}
              id={`${id}-enabled`}
              checked={enabled}
              disabled={!canEnable && !enabled}
              onCheckedChange={setEnabled}
            />
            <FieldLabel htmlFor={`${id}-enabled`}>启用规则</FieldLabel>
          </UI.Content>
          <FieldDescription>
            规则默认关闭；保存不会发送测试通知。通知发送及目标验证需要各自就绪。
          </FieldDescription>
        </Field>
      </FieldGroup>
      <UI.Content className="flex gap-3">
        <Button
          type="submit"
          disabled={busy || !sources.topics.length || !sources.targets.length}
          aria-busy={busy}
        >
          {busy && <Spinner aria-hidden="true" data-icon="inline-start" />}
          {busy ? "正在保存…" : "保存规则"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            toast.info("已取消编辑。");
            cancel();
          }}
          disabled={busy}
        >
          取消
        </Button>
      </UI.Content>
    </UI.Form>
  );
}

export function AlertsWorkspace() {
  const [data, setData] = useState<
    (Sources & { rules: HotKeyAPI.AlertRuleView[] }) | null
  >(null);
  const [error, setError] = useState<MonitorFailure | null>(null);
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
        if (caught instanceof ApiRequestError && caught.kind === "cancelled")
          return;
        if (generation.current === request)
          setError(readMonitorFailure(caught, "告警配置读取失败，请重试。"));
      });
  }, []);
  useEffect(() => {
    void load();
    return () => {
      generation.current += 1;
    };
  }, [load]);
  return (
    <UI.Content className="flex min-w-0 flex-col gap-8">
      <UI.Content className="flex flex-col gap-3">
        <UI.Heading level={1}>突发告警</UI.Heading>
        <UI.Text tone="muted" size="sm">
          使用已取得且许可有效的材料评估规则，查看触发与冷却记录。无法判定和送达未知分别记录；未知送达不会自动重发。
        </UI.Text>
      </UI.Content>
      <Alert role="status">
        <AlertDescription>
          每五分钟评估已启用规则：最近一小时有效负面计数，或指定事件的同公式可比热度增量达到阈值后，进入规则设定的冷却期。缺少分析或可比快照时保留“无法判定”，送达未知不会自动重发。
        </AlertDescription>
      </Alert>
      <Separator />
      {error && (
        <PageState
          state={error.forbidden ? "forbidden" : data ? "stale" : "error"}
          eyebrow="突发告警"
          title={error.forbidden ? "无权读取告警配置" : "暂时无法读取告警配置"}
          description={
            error.forbidden
              ? "请登录有权访问告警的账户。"
              : "请重试加载，当前编辑内容会保留。"
          }
          errorCode={error.code}
          httpStatus={error.httpStatus}
          action={
            error.forbidden ? undefined : (
              <Button variant="outline" onClick={() => void load()}>
                重试加载
              </Button>
            )
          }
        />
      )}
      {!data
        ? !error && (
            <PageState
              state="loading"
              loadingLayout="detail"
              eyebrow="突发告警"
              title="正在读取告警配置"
              description="正在读取规则、主题和通知目标。"
            />
          )
        : !error?.forbidden && (
            <>
              {!data.topics.length && (
                <UI.Text>
                  先
                  <Button asChild variant="link">
                    <Link href="/monitors/new">创建关注方向</Link>
                  </Button>
                  ，再配置告警规则。
                </UI.Text>
              )}
              {!data.targets.length && (
                <UI.Text>
                  尚无通知目标。请在
                  <Button asChild variant="link">
                    <Link href="/operations">运营与通知</Link>
                  </Button>
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
                <PageState
                  state="empty"
                  eyebrow="突发告警"
                  title="尚未配置告警规则"
                  description="当前不会发送告警。先准备监控主题与获准的通知目标，再新建规则。"
                  action={
                    <Button
                      type="button"
                      variant="outline"
                      disabled={
                        editing !== null ||
                        !data.topics.length ||
                        !data.targets.length
                      }
                      onClick={() => setEditing("new")}
                    >
                      配置第一条规则
                    </Button>
                  }
                />
              ) : (
                <ItemGroup>
                  {data.rules.map((rule) => (
                    <UI.Content
                      as="section"
                      role="listitem"
                      key={rule.id}
                      className="flex min-w-0 flex-col gap-4"
                    >
                      <Separator />
                      <UI.Content className="flex flex-wrap items-start justify-between gap-4">
                        <UI.Content className="flex min-w-0 flex-col gap-3">
                          <UI.Content className="flex flex-wrap items-center gap-3">
                            <UI.Heading level={2}>{rule.name}</UI.Heading>
                            <Badge variant="secondary">
                              {rule.enabled ? "已启用" : "已关闭"}
                            </Badge>
                          </UI.Content>
                          <UI.Text tone="muted" size="sm">
                            {data.topics.find(
                              (topic) => topic.id === rule.topic_id,
                            )?.name ?? "主题不可用"}
                          </UI.Text>
                          <AlertRuleSummary rule={rule} />
                          {rule.readiness === "blocked" && (
                            <UI.Text tone="muted" size="sm">
                              {alertReasonLabel(rule.reason)}
                            </UI.Text>
                          )}
                        </UI.Content>
                        <UI.Content className="flex gap-2">
                          <Button
                            variant="outline"
                            onClick={() => setEditing(rule)}
                          >
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
                      {historyId === rule.id && (
                        <AlertHistory key={rule.id} ruleId={rule.id} />
                      )}
                    </UI.Content>
                  ))}
                </ItemGroup>
              )}
            </>
          )}
    </UI.Content>
  );
}

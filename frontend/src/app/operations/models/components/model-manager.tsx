"use client";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  SelectLabel,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from "@/components/ui/select";
import { Field, FieldLabel } from "@/components/ui/field";

import { useRef, useState } from "react";
import {
  acknowledgeAiCostCircuit,
  getAiModelConfiguration,
  getAiModelOverview,
  switchAiCapabilityModel,
} from "@/api/moxingpeizhi";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError } from "@/request";

const sourceLabels = {
  admin: "运营覆盖",
  env: "环境配置",
  default: "服务端默认",
};
const money = (value: number | null, currency: string | null) =>
  value === null
    ? "未记录"
    : `${currency ?? "币种未声明"} ${(value / 1_000_000).toFixed(6)}`;
const time = (value: string | null) =>
  value
    ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })
    : "暂无";

function auditModel(
  state: HotKeyAPI.OperatorAuditView["after_state"],
  target: string,
) {
  const capability = target.startsWith("capability:")
    ? target.slice(11)
    : undefined;
  if (!capability || !Array.isArray(state.capabilities)) return null;
  const choice = state.capabilities.find(
    (value: unknown) =>
      typeof value === "object" &&
      value !== null &&
      "key" in value &&
      value.key === capability,
  ) as unknown;
  if (typeof choice !== "object" || choice === null || !("current" in choice))
    return null;
  const current = choice.current;
  if (
    typeof current !== "object" ||
    current === null ||
    !("provider" in current) ||
    !("model" in current) ||
    typeof current.provider !== "string" ||
    typeof current.model !== "string"
  )
    return null;
  return `${current.provider}/${current.model}`;
}

function CapabilityCard({
  capability,
  configuration,
  busy,
  save,
}: {
  capability: HotKeyAPI.AiCapabilityChoice;
  configuration: HotKeyAPI.AiModelConfigurationView;
  busy: boolean;
  save: (body: Omit<HotKeyAPI.AiModelSwitchInput, "operation_id">) => void;
}) {
  const [model, setModel] = useState(
    configuration.choices.some(
      (choice) => choice.key === capability.current.key,
    )
      ? capability.current.key
      : "",
  );
  const [reason, setReason] = useState("");
  return (
    <section className="bg-muted/30 flex min-w-0 flex-col gap-y-4 rounded-xl p-5">
      <h2 className="font-medium">{capability.label}</h2>
      <p className="text-muted-foreground text-sm">
        当前 {capability.current.provider} / {capability.current.model} ·{" "}
        {sourceLabels[capability.source]} ·{" "}
        {capability.current.vision ? "支持视觉输入" : "文本输入"}
      </p>
      <p className="text-muted-foreground text-xs">
        {capability.env} · 默认 {capability.default_model ?? "default"}
      </p>
      <Field className="min-w-0" data-disabled={busy}>
        <FieldLabel htmlFor={`model-${capability.key}`}>
          {capability.label} 目标模型
        </FieldLabel>
        <Select
          value={model}
          disabled={busy}
          onValueChange={(selectedValue) =>
            setModel(selectedValue === "__none__" ? "" : selectedValue)
          }
        >
          <SelectTrigger
            id={`model-${capability.key}`}
            className="w-full min-w-0"
          >
            <SelectValue placeholder="继承环境或服务端默认（清除运营覆盖）" />
          </SelectTrigger>
          <SelectContent position="popper">
            <SelectGroup>
              <SelectLabel className="sr-only">
                {capability.label} 目标模型
              </SelectLabel>
              <SelectItem value="__none__" className="whitespace-normal">
                继承环境或服务端默认（清除运营覆盖）
              </SelectItem>
              {configuration.choices.map((choice) => (
                <SelectItem
                  key={choice.key}
                  disabled={!choice.configured}
                  value={choice.key}
                  className="whitespace-normal"
                >
                  {choice.key} · {choice.provider}/{choice.model} ·{" "}
                  {choice.vision ? "视觉" : "文本"}
                  {choice.configured ? "" : " · 尚未配置"}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      </Field>
      <Field className="min-w-0" data-disabled={busy}>
        <FieldLabel htmlFor={`reason-${capability.key}`}>
          {capability.label} 切换原因
        </FieldLabel>
        <Textarea
          id={`reason-${capability.key}`}
          value={reason}
          disabled={busy}
          maxLength={1000}
          onChange={(event) => setReason(event.target.value)}
        />
      </Field>
      <Button
        variant="outline"
        disabled={busy || !reason.trim()}
        onClick={() =>
          save({
            expected_version: configuration.version,
            capability: capability.key,
            model_key: model || null,
            reason: reason.trim(),
            actor: "Workspace operator",
          })
        }
      >
        保存 {capability.label}
      </Button>
    </section>
  );
}

function CostCircuitCard({
  circuit,
  version,
  busy,
  acknowledge,
}: {
  circuit: HotKeyAPI.AiCostCircuitView;
  version: number;
  busy: boolean;
  acknowledge: (
    body: Omit<HotKeyAPI.AiCostCircuitAckInput, "operation_id">,
  ) => void;
}) {
  const [reason, setReason] = useState("");
  return (
    <section className="bg-muted/30 flex flex-col gap-y-3 rounded-lg p-4">
      <p className="text-sm font-medium">
        {circuit.provider}/{circuit.model} ·{" "}
        {circuit.acknowledged ? "已人工核对" : "成本熔断待核对"}
      </p>
      <p className="text-muted-foreground text-xs">
        调用 {circuit.call_id} · {time(circuit.created_at)}
      </p>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt>供应商实际</dt>
          <dd>{money(circuit.cost_actual_micros, circuit.currency)}</dd>
        </div>
        <div>
          <dt>冻结上限</dt>
          <dd>{money(circuit.cost_cap_micros, circuit.currency)}</dd>
        </div>
      </dl>
      {!circuit.acknowledged ? (
        <>
          <Label htmlFor={`ack-${circuit.call_id}`}>
            成本核对原因 {circuit.call_id}
          </Label>
          <Textarea
            id={`ack-${circuit.call_id}`}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            maxLength={1000}
            disabled={busy}
          />
          <Button
            disabled={busy || !reason.trim()}
            variant="outline"
            onClick={() =>
              acknowledge({
                call_id: circuit.call_id,
                expected_version: version,
                reason: reason.trim(),
              })
            }
          >
            确认已核对该调用成本
          </Button>
        </>
      ) : null}
    </section>
  );
}

export function ModelManager() {
  const [token, setToken] = useState("");
  const [days, setDays] = useState(7);
  const [configuration, setConfiguration] =
    useState<HotKeyAPI.AiModelConfigurationView | null>(null);
  const [overview, setOverview] = useState<HotKeyAPI.AiModelOverview | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const context = useRef(0);
  const operations = useRef(new Map<string, string>());
  const active = useRef(false);
  function changeToken(value: string) {
    context.current += 1;
    active.current = false;
    operations.current.clear();
    setToken(value);
    setConfiguration(null);
    setOverview(null);
    setBusy(false);
    setError("");
    setNotice("");
  }
  const headers = { "X-HotKey-Operator-Token": token, "X-HotKey-CSRF": "1" };
  function operation(body: object) {
    const key = JSON.stringify(body);
    if (!operations.current.has(key))
      operations.current.set(key, crypto.randomUUID());
    return operations.current.get(key)!;
  }
  async function read(captured: number, readHeaders: typeof headers) {
    const [value, stats] = await Promise.all([
      getAiModelConfiguration({ headers: readHeaders }),
      getAiModelOverview({ days }, { headers: readHeaders }),
    ]);
    if (captured !== context.current) return;
    if (value.version !== stats.configuration.version)
      throw new ApiRequestError({
        kind: "http",
        status: 409,
        code: "ai_configuration_conflict",
        message: "配置已变化，请重新读取。",
      });
    setConfiguration(value);
    setOverview(stats);
  }
  async function perform(
    action: (captured: number, readHeaders: typeof headers) => Promise<void>,
    operationId?: string,
  ) {
    if (!token.trim() || active.current) return;
    const captured = context.current,
      readHeaders = { ...headers };
    active.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action(captured, readHeaders);
    } catch (cause) {
      if (captured !== context.current) return;
      const known = cause instanceof ApiRequestError;
      const conflict = known && cause.code === "ai_configuration_conflict";
      const uncertain =
        known && ["network", "timeout", "protocol"].includes(cause.kind);
      setError(
        `${conflict ? "配置版本已变化，请重新读取后再修改。" : known ? cause.message : "暂时无法完成操作，请重新读取。"}${known && cause.requestId ? ` 请求编号：${cause.requestId}` : ""}${uncertain && operationId ? ` 结果尚未确认，操作编号：${operationId}。重试相同输入将复用此编号。` : ""}`,
      );
    } finally {
      if (captured === context.current) {
        active.current = false;
        setBusy(false);
      }
    }
  }
  function save(body: Omit<HotKeyAPI.AiModelSwitchInput, "operation_id">) {
    const operationId = operation(body);
    void perform(async (captured, readHeaders) => {
      const result = await switchAiCapabilityModel(
        { ...body, operation_id: operationId },
        { headers: readHeaders },
      );
      if (captured !== context.current) return;
      await read(captured, readHeaders);
      if (captured === context.current)
        setNotice(
          `切换已记录，返回配置版本 ${result.version}。仅之后受理的任务采用新配置。`,
        );
    }, operationId);
  }
  function acknowledge(
    body: Omit<HotKeyAPI.AiCostCircuitAckInput, "operation_id">,
  ) {
    const operationId = operation(body);
    void perform(async (captured, readHeaders) => {
      await acknowledgeAiCostCircuit(
        { ...body, operation_id: operationId },
        { headers: readHeaders },
      );
      if (captured !== context.current) return;
      await read(captured, readHeaders);
      if (captured === context.current)
        setNotice(
          "具体调用的成本核对已记录。未知调用仍保持未知，不会因核对自动重发。",
        );
    }, operationId);
  }
  return (
    <>
      <div className="flex flex-col gap-y-8">
        <header className="flex flex-col gap-y-3">
          <h1 className="text-3xl font-medium tracking-tight">
            模型配置与费用
          </h1>
          <p className="text-muted-foreground text-sm">
            11
            个能力独立配置；已受理任务保留原模型与预算。读取配置不会调用模型。
          </p>
        </header>
        <section className="flex flex-wrap items-end gap-3">
          <Field className="min-w-0 flex-1 basis-full gap-2 sm:basis-64">
            <FieldLabel htmlFor="operator-token">操作员令牌</FieldLabel>
            <Input
              id="operator-token"
              type="password"
              value={token}
              autoComplete="off"
              onChange={(event) => changeToken(event.target.value)}
            />
          </Field>
          <Button variant="outline" onClick={() => changeToken("")}>
            清除令牌
          </Button>
          <Field className="w-28" data-disabled={busy}>
            <FieldLabel htmlFor="days">统计天数</FieldLabel>
            <Input
              id="days"
              type="number"
              min={1}
              max={90}
              value={days}
              disabled={busy}
              onChange={(event) =>
                setDays(
                  Math.max(1, Math.min(90, Number(event.target.value) || 1)),
                )
              }
            />
          </Field>
          <Button
            disabled={!token.trim() || busy}
            onClick={() => void perform(read)}
          >
            读取模型配置
          </Button>
        </section>
        <p className="text-muted-foreground text-xs">
          令牌只保存在本页内存，清除或离开页面后不再保留。
        </p>
        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        {notice ? (
          <p role="status" className="text-sm">
            {notice}
          </p>
        ) : null}
        {busy ? <p role="status">正在读取或提交…</p> : null}
        {configuration ? (
          <>
            <section className="flex flex-col gap-y-2">
              <h2 className="font-medium">配置版本 {configuration.version}</h2>
              <p className="text-muted-foreground text-sm">
                {configuration.calls_enabled
                  ? "模型调用已启用"
                  : "模型调用已关闭"}{" "}
                ·{" "}
                {configuration.paid_requests_enabled
                  ? "付费请求已启用"
                  : "付费请求已关闭"}{" "}
                ·{" "}
                {configuration.compatible_requests_enabled
                  ? "兼容API已启用"
                  : "兼容API已关闭"}
              </p>
              <p className="text-muted-foreground text-sm">
                这些开关是当前执行许可。模型目录的视觉声明表示输入能力，质量与真实供应商可用性需独立验证。
              </p>
            </section>
            <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
              {configuration.capabilities.map((capability) => (
                <CapabilityCard
                  key={`${capability.key}:${configuration.version}`}
                  capability={capability}
                  configuration={configuration}
                  busy={busy}
                  save={save}
                />
              ))}
            </div>
          </>
        ) : (
          <p className="text-muted-foreground">
            输入操作员令牌并读取服务端配置。
          </p>
        )}
        {overview ? (
          <>
            <section className="flex flex-col gap-y-4">
              <h2 className="text-xl font-medium">
                原调用账本 · 最近 {overview.days} 天
              </h2>
              <p className="text-muted-foreground text-sm">
                估计、供应商实际与冻结上限分列；币种分别显示。未知结果不计作成功。
              </p>
              {overview.usage.length ? (
                <div className="flex flex-col gap-y-4">
                  {overview.usage.map((row, index) => (
                    <article
                      key={`${row.purpose}:${row.provider}:${row.model}:${row.currency}:${index}`}
                      className="bg-muted/30 flex flex-col gap-y-3 rounded-lg p-4"
                    >
                      <p className="text-sm font-medium">
                        {row.capability} · {row.provider}/{row.model} ·{" "}
                        {row.prompt_version}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        {row.purpose} · 调用 {row.calls} · 成功 {row.succeeded}{" "}
                        · 失败 {row.failed} ·{" "}
                        <span>进行中 {row.running ?? 0}</span> ·{" "}
                        <span>未知 {row.unknown}</span>
                      </p>
                      <dl className="grid gap-3 text-sm sm:grid-cols-3">
                        <div>
                          <dt>估计费用</dt>
                          <dd>
                            {money(row.cost_estimate_micros, row.currency)}
                          </dd>
                        </div>
                        <div>
                          <dt>供应商实际</dt>
                          <dd>{money(row.cost_actual_micros, row.currency)}</dd>
                        </div>
                        <div>
                          <dt>冻结上限</dt>
                          <dd>{money(row.cost_cap_micros, row.currency)}</dd>
                        </div>
                        <div>
                          <dt>输入 / 缓存 / 输出 token</dt>
                          <dd>
                            {row.input_tokens} / {row.cached_input_tokens} /{" "}
                            {row.output_tokens}
                          </dd>
                        </div>
                        <div>
                          <dt>延迟 p50 / p95</dt>
                          <dd>
                            {row.latency_p50_ms ?? "未知"} /{" "}
                            {row.latency_p95_ms ?? "未知"} ms
                          </dd>
                        </div>
                      </dl>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground text-sm">
                  这段时间没有原调用记录。
                </p>
              )}
            </section>
            <section className="flex flex-col gap-y-4">
              <h2 className="text-xl font-medium">成本熔断核对</h2>
              <p className="text-muted-foreground text-sm">
                按具体超额调用与当前配置版本核对，只解除该成本阻断。
              </p>
              {overview.cost_circuits?.length && configuration ? (
                overview.cost_circuits.map((circuit) => (
                  <CostCircuitCard
                    key={`${circuit.call_id}:${configuration.version}`}
                    circuit={circuit}
                    version={configuration.version}
                    busy={busy}
                    acknowledge={acknowledge}
                  />
                ))
              ) : (
                <p className="text-muted-foreground text-sm">
                  没有需要核对的超额调用。
                </p>
              )}
            </section>
            <section className="flex flex-col gap-y-4">
              <h2 className="text-xl font-medium">配置与成本核对审计</h2>
              {overview.history.length ? (
                <ul className="flex flex-col gap-y-4">
                  {overview.history.map((entry) => (
                    <li
                      key={entry.id}
                      className="bg-muted/30 rounded-lg p-4 text-sm"
                    >
                      <p>
                        {entry.action} · {entry.target_ref} · {entry.status}
                      </p>
                      <p>{entry.reason}</p>
                      <p className="text-muted-foreground text-xs">
                        版本{" "}
                        {typeof entry.before_state.version === "number"
                          ? entry.before_state.version
                          : "未知"}{" "}
                        →{" "}
                        {typeof entry.after_state.version === "number"
                          ? entry.after_state.version
                          : "未知"}
                        {auditModel(entry.before_state, entry.target_ref) &&
                        auditModel(entry.after_state, entry.target_ref)
                          ? ` · ${auditModel(entry.before_state, entry.target_ref)} → ${auditModel(entry.after_state, entry.target_ref)}`
                          : ""}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        {entry.actor} · {time(entry.created_at)} · 操作{" "}
                        {entry.operation_id}
                        {entry.error_code ? ` · ${entry.error_code}` : ""}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground text-sm">
                  尚无配置切换或成本核对记录。
                </p>
              )}
            </section>
          </>
        ) : null}
      </div>
    </>
  );
}

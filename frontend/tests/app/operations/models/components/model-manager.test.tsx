import { selectOption } from "../../../../select";
// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/request";
import { ModelManager } from "@/app/operations/models/components/model-manager";

const api = vi.hoisted(() => ({
  configuration: vi.fn(),
  overview: vi.fn(),
  switchModel: vi.fn(),
  ack: vi.fn(),
}));
vi.mock("@/api/moxingpeizhi", () => ({
  getAiModelConfiguration: api.configuration,
  getAiModelOverview: api.overview,
  switchAiCapabilityModel: api.switchModel,
  acknowledgeAiCostCircuit: api.ack,
}));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  localStorage.clear();
});
const keys: HotKeyAPI.AiCapabilityChoice["key"][] = [
  "prefilter",
  "score",
  "understand",
  "summarize",
  "structure",
  "group",
  "groupReview",
  "digest",
  "report",
  "translate",
  "monitor",
];
const config: HotKeyAPI.AiModelConfigurationView = {
  version: 3,
  created_at: null,
  calls_enabled: false,
  paid_requests_enabled: false,
  compatible_requests_enabled: false,
  capabilities: keys.map((key) => ({
    key,
    label: key,
    env: `${key.toUpperCase()}_MODEL`,
    current: {
      key: "default",
      provider: "controlled",
      model: "original",
      component_key: "controlled",
      vision: false,
      catalog_sha256: "a".repeat(64),
    },
    source: "default",
  })),
  choices: [
    {
      key: "default",
      provider: "controlled",
      model: "original",
      vision: false,
      configured: true,
      component_key: "controlled",
      currency: null,
      input_rate_micros_per_million: null,
      output_rate_micros_per_million: null,
    },
    {
      key: "vision",
      provider: "controlled",
      model: "vision-model",
      vision: true,
      configured: true,
      component_key: "controlled.vision",
      currency: "USD",
      input_rate_micros_per_million: "1",
      output_rate_micros_per_million: "2",
    },
  ],
};
const overview: HotKeyAPI.AiModelOverview = {
  days: 7,
  configuration: config,
  history: [],
  usage: [
    {
      capability: "score",
      purpose: "score_article",
      provider: "controlled",
      model: "original",
      prompt_version: "v1",
      calls: 5,
      succeeded: 1,
      failed: 1,
      unknown: 1,
      running: 2,
      latency_p50_ms: 20,
      latency_p95_ms: 50,
      input_tokens: 12,
      cached_input_tokens: 2,
      output_tokens: 4,
      currency: "USD",
      cost_estimate_micros: 10000,
      cost_actual_micros: 25000,
      cost_cap_micros: 50000,
    },
  ],
};
async function load() {
  api.configuration.mockResolvedValue(config);
  api.overview.mockResolvedValue(overview);
  render(<ModelManager />);
  fireEvent.change(screen.getByLabelText("操作员令牌"), {
    target: { value: "controlled-secret" },
  });
  fireEvent.click(screen.getByRole("button", { name: "读取模型配置" }));
  await screen.findByText("配置版本 3");
}
it("makes no anonymous call, reads all 11 capabilities and keeps costs, unknown and request switches truthful", async () => {
  render(<ModelManager />);
  expect(
    screen
      .getByRole("button", { name: "读取模型配置" })
      .hasAttribute("disabled"),
  ).toBe(true);
  expect(api.configuration).not.toHaveBeenCalled();
  cleanup();
  await load();
  expect(screen.getAllByRole("combobox", { name: /目标模型/ })).toHaveLength(
    11,
  );
  expect(screen.getByText(/模型调用已关闭/)).toBeTruthy();
  expect(screen.getByText("未知 1")).toBeTruthy();
  expect(screen.getByText("进行中 2")).toBeTruthy();
  expect(screen.getByText("USD 0.010000")).toBeTruthy();
  expect(screen.getByText("USD 0.025000")).toBeTruthy();
  expect(screen.getByText("USD 0.050000")).toBeTruthy();
  expect(localStorage.length).toBe(0);
  expect(api.configuration).toHaveBeenCalledWith({
    headers: {
      "X-HotKey-Operator-Token": "controlled-secret",
      "X-HotKey-CSRF": "1",
    },
  });
});
it("captures version/reason/inherit-null and reuses the same operation after an uncertain response", async () => {
  await load();
  api.switchModel.mockRejectedValueOnce(
    new ApiRequestError({ kind: "timeout", message: "timeout" }),
  );
  api.switchModel.mockResolvedValueOnce({ ...config, version: 4 });
  await selectOption(
    screen.getByLabelText("score 目标模型"),
    "继承环境或服务端默认（清除运营覆盖）",
  );
  fireEvent.change(screen.getByLabelText("score 切换原因"), {
    target: { value: "恢复环境选择" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存 score" }));
  await screen.findByText(/结果尚未确认/);
  const body = api.switchModel.mock.calls[0][0];
  expect(body).toMatchObject({
    capability: "score",
    expected_version: 3,
    model_key: null,
    reason: "恢复环境选择",
  });
  fireEvent.click(screen.getByRole("button", { name: "保存 score" }));
  await waitFor(() => expect(api.switchModel).toHaveBeenCalledTimes(2));
  expect(api.switchModel.mock.calls[1][0].operation_id).toBe(body.operation_id);
});
it("clears protected state and ignores a late response after the operator token is removed", async () => {
  let finish!: (value: HotKeyAPI.AiModelConfigurationView) => void;
  api.configuration.mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  api.overview.mockResolvedValue(overview);
  render(<ModelManager />);
  fireEvent.change(screen.getByLabelText("操作员令牌"), {
    target: { value: "old" },
  });
  fireEvent.click(screen.getByRole("button", { name: "读取模型配置" }));
  fireEvent.click(screen.getByRole("button", { name: "清除令牌" }));
  finish(config);
  await waitFor(() => expect(screen.queryByText("配置版本 3")).toBeNull());
  expect((screen.getByLabelText("操作员令牌") as HTMLInputElement).value).toBe(
    "",
  );
  expect(localStorage.length).toBe(0);
});

it("acknowledges the exact cost circuit with captured config CAS and preserves unknown outcomes", async () => {
  const circuit: HotKeyAPI.AiCostCircuitView = {
    call_id: "00000000-0000-4000-8000-000000000019",
    provider: "controlled",
    model: "original",
    currency: "CNY",
    cost_actual_micros: 120000,
    cost_cap_micros: 100000,
    acknowledged: false,
    created_at: "2026-10-02T00:00:00Z",
  };
  await load();
  api.overview.mockResolvedValue({ ...overview, cost_circuits: [circuit] });
  fireEvent.click(screen.getByRole("button", { name: "读取模型配置" }));
  await screen.findByText("成本熔断待核对", { exact: false });
  api.ack.mockResolvedValue(config);
  api.overview.mockResolvedValue({
    ...overview,
    cost_circuits: [{ ...circuit, acknowledged: true }],
  });
  fireEvent.change(screen.getByLabelText(`成本核对原因 ${circuit.call_id}`), {
    target: { value: "核对供应商原回执" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认已核对该调用成本" }));
  await screen.findByText(/具体调用的成本核对已记录/);
  expect(api.ack.mock.calls[0][0]).toMatchObject({
    expected_version: 3,
    call_id: circuit.call_id,
    reason: "核对供应商原回执",
  });
  expect(api.ack.mock.calls[0][1]).toEqual({
    headers: {
      "X-HotKey-Operator-Token": "controlled-secret",
      "X-HotKey-CSRF": "1",
    },
  });
  expect(screen.getByText("未知 1")).toBeTruthy();
  expect(screen.getByText("CNY 0.120000")).toBeTruthy();
  expect(
    screen.queryByRole("button", { name: "确认已核对该调用成本" }),
  ).toBeNull();
  expect(api.switchModel).not.toHaveBeenCalled();
});

it("keeps the previous configuration visible after a stale-version rejection without claiming success", async () => {
  await load();
  api.switchModel.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      status: 409,
      code: "ai_configuration_conflict",
      message: "conflict",
    }),
  );
  fireEvent.change(screen.getByLabelText("score 目标模型"), {
    target: { value: "vision" },
  });
  fireEvent.change(screen.getByLabelText("score 切换原因"), {
    target: { value: "受控切换" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存 score" }));
  await screen.findByText(/配置版本已变化/);
  expect(screen.getByText("配置版本 3")).toBeTruthy();
  expect(screen.queryByText(/切换已记录/)).toBeNull();
  expect(api.configuration).toHaveBeenCalledTimes(1);
});

it("shows embedding ledger costs in their own currency and the actual model-switch audit without an extra configuration card", async () => {
  await load();
  const changed = {
    ...config,
    version: 4,
    capabilities: config.capabilities.map((entry) =>
      entry.key === "score"
        ? { ...entry, current: { ...entry.current, model: "vision-model" } }
        : entry,
    ),
  };
  api.overview.mockResolvedValue({
    ...overview,
    usage: [
      ...overview.usage,
      {
        ...overview.usage[0],
        capability: "embedding",
        purpose: "events.embedding",
        provider: "jina",
        model: "owned-embedding",
        currency: "CNY",
        cost_estimate_micros: 20000,
        cost_actual_micros: 30000,
        cost_cap_micros: 60000,
      },
    ],
    history: [
      {
        id: "audit",
        operation_id: "operation",
        action: "models.switch",
        target_ref: "capability:score",
        actor: "Workspace operator",
        reason: "受控模型升级",
        status: "succeeded",
        before_state: config,
        after_state: changed,
        job_id: null,
        error_code: null,
        created_at: "2026-10-02T00:00:00Z",
        updated_at: "2026-10-02T00:00:00Z",
      },
    ],
  });
  fireEvent.click(screen.getByRole("button", { name: "读取模型配置" }));
  await screen.findByText(/embedding · jina\/owned-embedding/);
  expect(screen.getAllByRole("combobox", { name: /目标模型/ })).toHaveLength(
    11,
  );
  expect(screen.getByText("CNY 0.020000")).toBeTruthy();
  expect(screen.getByText("CNY 0.030000")).toBeTruthy();
  expect(screen.getByText("USD 0.025000")).toBeTruthy();
  expect(
    screen.getByText(
      /版本 3 → 4 · controlled\/original → controlled\/vision-model/,
    ),
  ).toBeTruthy();
});

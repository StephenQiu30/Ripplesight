// @vitest-environment happy-dom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({
  health: vi.fn(),
  maintenance: vi.fn(),
  feedback: vi.fn(),
  audit: vi.fn(),
  dictionaries: vi.fn(),
  save: vi.fn(),
  selectBench: vi.fn(),
}));
vi.mock("@/api/yunyingweihu", () => ({
  getOperationsHealth: api.health,
  getOperatorMaintenance: api.maintenance,
  listOperatorFeedback: api.feedback,
  listOperatorAudit: api.audit,
  listOperatorDictionaries: api.dictionaries,
  saveOperatorDictionary: api.save,
  listOperatorSelectBench: api.selectBench,
}));
vi.mock("./source-identity-editor", () => ({
  SourceIdentityEditor: () => null,
}));
vi.mock("./notification-workspace", () => ({
  NotificationWorkspace: () => null,
}));
vi.mock("./selectbench-reading", () => ({ SelectBenchReading: () => null }));
vi.mock("@/components/navigation/workspace-header", () => ({
  WorkspaceHeader: () => null,
}));
import { OperationsWorkspace } from "./operations-workspace";
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
it("makes no operator request before token entry and writes a dictionary with its current version", async () => {
  api.health.mockResolvedValue({
    heartbeats: [],
    failure_issues: [],
    budgets: [],
    feedback_new_count: 0,
    feedback_reviewing_count: 0,
    maintenance_enabled: false,
    backup_configured: false,
    feedback_forward_enabled: false,
  });
  api.maintenance.mockResolvedValue({
    schedules: [],
    findings: [],
    backups: [],
  });
  api.feedback.mockResolvedValue({ items: [], next_cursor: null });
  api.audit.mockResolvedValue({ items: [], next_cursor: null });
  api.dictionaries.mockResolvedValue([
    { id: "d", kind: "glossary", version: 4, content: { Acme: ["艾克米"] } },
  ]);
  api.save.mockResolvedValue({ version: 5 });
  api.selectBench.mockResolvedValue({ items: [], next_cursor: null });
  render(<OperationsWorkspace />);
  expect(api.health).not.toHaveBeenCalled();
  expect(api.selectBench).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("运营 Token"), {
    target: { value: "operator-secret" },
  });
  fireEvent.click(screen.getByRole("button", { name: "进入运营工作区" }));
  await screen.findByText("维护调度已关闭");
  expect(api.health).toHaveBeenCalledWith(
    expect.objectContaining({
      headers: { "X-HotKey-Operator-Token": "operator-secret" },
    }),
  );
  fireEvent.change(screen.getByLabelText("词典修改原因"), {
    target: { value: "确认别名" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存词典新版本" }));
  await waitFor(() =>
    expect(api.save).toHaveBeenCalledWith(
      expect.objectContaining({
        expected_version: 4,
        reason: "确认别名",
        content: { Acme: ["艾克米"] },
      }),
      expect.anything(),
    ),
  );
});

function prepareWorkspace() {
  api.health.mockResolvedValue({
    heartbeats: [],
    failure_issues: [],
    budgets: [],
    feedback_new_count: 0,
    feedback_reviewing_count: 0,
    maintenance_enabled: false,
    backup_configured: false,
    feedback_forward_enabled: false,
  });
  api.maintenance.mockResolvedValue({
    schedules: [],
    findings: [],
    backups: [],
  });
  api.feedback.mockResolvedValue({ items: [], next_cursor: null });
  api.audit.mockResolvedValue({ items: [], next_cursor: null });
  api.dictionaries.mockResolvedValue([
    { id: "d", kind: "glossary", version: 4, content: { Acme: ["艾克米"] } },
  ]);
  api.selectBench.mockResolvedValue({ items: [], next_cursor: null });
}

function deferred() {
  let resolve!: (value: unknown) => void;
  const promise = new Promise<unknown>((finish) => {
    resolve = finish;
  });
  return { promise, resolve };
}

async function enterWorkspace() {
  fireEvent.change(screen.getByLabelText("运营 Token"), {
    target: { value: "operator-secret" },
  });
  fireEvent.click(screen.getByRole("button", { name: "进入运营工作区" }));
  await screen.findByText("维护调度已关闭");
}

it("keeps the operator logged out after an in-flight refresh resolves", async () => {
  prepareWorkspace();
  render(<OperationsWorkspace />);
  await enterWorkspace();
  const late = deferred();
  api.health.mockImplementationOnce(() => late.promise);
  fireEvent.click(screen.getByRole("button", { name: "刷新运营状态" }));
  expect(api.health).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole("button", { name: "退出运营工作区" }));
  expect(screen.getByLabelText("运营 Token")).toHaveProperty("value", "");
  await act(async () => {
    late.resolve({
      heartbeats: [],
      failure_issues: [],
      budgets: [],
      feedback_new_count: 99,
      feedback_reviewing_count: 0,
      maintenance_enabled: true,
      backup_configured: true,
      feedback_forward_enabled: true,
    });
  });
  await waitFor(() => expect(screen.queryByText("维护调度已开启")).toBeNull());
  expect(screen.queryByRole("button", { name: "退出运营工作区" })).toBeNull();
  expect(screen.getByRole("button", { name: "进入运营工作区" })).toHaveProperty(
    "disabled",
    false,
  );
});

it("does not issue a refresh from a mutation that completes after operator exit", async () => {
  prepareWorkspace();
  const late = deferred();
  api.save.mockImplementationOnce(() => late.promise);
  render(<OperationsWorkspace />);
  await enterWorkspace();
  fireEvent.change(screen.getByLabelText("词典修改原因"), {
    target: { value: "确认别名" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存词典新版本" }));
  await waitFor(() => expect(api.save).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "退出运营工作区" }));
  await act(async () => {
    late.resolve({ version: 5 });
  });
  await waitFor(() => expect(api.health).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole("button", { name: "退出运营工作区" })).toBeNull();
  expect(screen.getByLabelText("运营 Token")).toHaveProperty("value", "");
});

it("ignores an old refresh after exit and a different operator login", async () => {
  prepareWorkspace();
  render(<OperationsWorkspace />);
  await enterWorkspace();
  const late = deferred();
  api.health.mockImplementationOnce(() => late.promise);
  fireEvent.click(screen.getByRole("button", { name: "刷新运营状态" }));
  fireEvent.click(screen.getByRole("button", { name: "退出运营工作区" }));
  api.health.mockResolvedValue({
    heartbeats: [],
    failure_issues: [],
    budgets: [],
    feedback_new_count: 0,
    feedback_reviewing_count: 0,
    maintenance_enabled: true,
    backup_configured: false,
    feedback_forward_enabled: false,
  });
  fireEvent.change(screen.getByLabelText("运营 Token"), {
    target: { value: "different-operator" },
  });
  fireEvent.click(screen.getByRole("button", { name: "进入运营工作区" }));
  await screen.findByText("维护调度已开启");
  await act(async () => {
    late.resolve({
      heartbeats: [],
      failure_issues: [],
      budgets: [],
      feedback_new_count: 99,
      feedback_reviewing_count: 0,
      maintenance_enabled: false,
      backup_configured: true,
      feedback_forward_enabled: true,
    });
  });
  expect(screen.queryByText("维护调度已关闭")).toBeNull();
  expect(screen.queryByText("备份已配置")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "刷新运营状态" }));
  await waitFor(() => expect(api.health).toHaveBeenCalledTimes(4));
  expect(api.health).toHaveBeenLastCalledWith({
    headers: { "X-HotKey-Operator-Token": "different-operator" },
  });
});

it("does not append an old private feedback page after a new operator login", async () => {
  prepareWorkspace();
  api.feedback.mockResolvedValueOnce({ items: [], next_cursor: "older-page" });
  render(<OperationsWorkspace />);
  await enterWorkspace();
  const late = deferred();
  api.feedback.mockImplementationOnce(() => late.promise);
  fireEvent.click(screen.getByRole("button", { name: "加载更多反馈" }));
  fireEvent.click(screen.getByRole("button", { name: "退出运营工作区" }));
  fireEvent.change(screen.getByLabelText("运营 Token"), {
    target: { value: "different-operator" },
  });
  fireEvent.click(screen.getByRole("button", { name: "进入运营工作区" }));
  await screen.findByText("维护调度已关闭");
  await act(async () => {
    late.resolve({
      items: [
        {
          id: "private-old-feedback",
          status: "new",
          revision: 1,
          banned: false,
          content: "旧运营上下文私有反馈",
          created_at: "2026-10-02T00:00:00Z",
        },
      ],
      next_cursor: "another-old-page",
    });
  });
  expect(screen.queryByText("旧运营上下文私有反馈")).toBeNull();
  expect(screen.queryByRole("button", { name: "加载更多反馈" })).toBeNull();
});

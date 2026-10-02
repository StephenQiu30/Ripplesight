// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { EditorialExternalIngress } from "@/app/editorial-sources/components/editorial-external-ingress";

const api = vi.hoisted(() => ({ submit: vi.fn(), read: vi.fn() }));
vi.mock("@/api/bianjilaiyuan", () => ({
  ingestExternalEditorialSource: api.submit,
  getExternalEditorialIngressReceipt: api.read,
}));
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);
const props = {
  profileId: "controlled-profile",
  expectedRevision: 8,
  configurationVersion: 4,
  enabled: true,
};
const receipt = {
  job: { id: "job-one", status: "queued" },
  profile_id: "controlled-profile",
  run_id: "run-one",
  configuration_version: 4,
  received: 1,
  items: [{ index: 0, status: "pending", identity_key: "one" }],
};
function fill(materials = '[{"identity_key":"one"}]') {
  fireEvent.change(screen.getByLabelText("来源专属令牌"), {
    target: { value: "controlled-source-token-12345678" },
  });
  fireEvent.change(screen.getByLabelText("材料 JSON 数组"), {
    target: { value: materials },
  });
}
it("shows pending admission and manually reads each fixed result using only the dedicated source token", async () => {
  api.submit.mockResolvedValue(receipt);
  api.read.mockResolvedValue({
    ...receipt,
    received: 3,
    items: [
      {
        index: 0,
        status: "succeeded",
        content_id: "content-one",
        content_version_id: "version-one",
        change: "created",
      },
      { index: 1, status: "duplicate", duplicate_of: 0 },
      { index: 2, status: "rejected", reason: "invalid_material" },
    ],
  });
  render(<EditorialExternalIngress {...props} />);
  fill();
  fireEvent.click(screen.getByRole("button", { name: "受理材料摄入" }));
  await screen.findByText(/等待处理/);
  expect(api.submit.mock.calls[0][1]).toMatchObject({
    expected_revision: 8,
    configuration_version: 4,
    operation_id: expect.any(String),
  });
  expect(api.submit.mock.calls[0][2]).toEqual({
    headers: {
      "X-HotKey-Source-Token": "controlled-source-token-12345678",
      "X-HotKey-CSRF": "1",
    },
  });
  expect(api.read).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "读取逐条摄入回执" }));
  await screen.findByText(/已保存 · created/);
  expect(
    screen
      .getByRole("link", { name: "读取材料 content-one" })
      .getAttribute("href"),
  ).toBe("/content/content-one");
  expect(screen.getByText(/重复 · 同批第 1 项/)).toBeTruthy();
  expect(screen.getByText(/已拒绝 · invalid_material/)).toBeTruthy();
  expect(api.read.mock.calls[0]).toEqual([
    { profile_id: "controlled-profile", run_id: "run-one" },
    {
      headers: {
        "X-HotKey-Source-Token": "controlled-source-token-12345678",
        "X-HotKey-CSRF": "1",
      },
    },
  ]);
  expect(api.submit).toHaveBeenCalledTimes(1);
});
it("enforces 50 items and four MiB before submission without preventing per-row invalid material receipts", async () => {
  render(<EditorialExternalIngress {...props} />);
  fill(JSON.stringify(Array.from({ length: 51 }, () => ({}))));
  fireEvent.click(screen.getByRole("button", { name: "受理材料摄入" }));
  await screen.findByText(/材料必须为 1—50 项/);
  expect(api.submit).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("材料 JSON 数组"), {
    target: { value: JSON.stringify([{ body: "中".repeat(1_398_102) }]) },
  });
  fireEvent.click(screen.getByRole("button", { name: "受理材料摄入" }));
  expect(api.submit).not.toHaveBeenCalled();
});
it("clears dedicated token context and discards a late admission rather than refilling its receipt", async () => {
  let complete!: (value: object) => void;
  api.submit.mockImplementation(
    () =>
      new Promise((resolve) => {
        complete = resolve;
      }),
  );
  render(<EditorialExternalIngress {...props} />);
  fill();
  fireEvent.click(screen.getByRole("button", { name: "受理材料摄入" }));
  await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "清除来源令牌与回执" }));
  complete(receipt);
  await waitFor(() =>
    expect(
      (screen.getByLabelText("来源专属令牌") as HTMLInputElement).value,
    ).toBe(""),
  );
  expect(screen.queryByRole("button", { name: "读取逐条摄入回执" })).toBeNull();
  expect(screen.queryByText(/等待处理/)).toBeNull();
});

it("blocks a 31-character source token and explicitly accepts the 32-character boundary", async () => {
  api.submit.mockResolvedValue(receipt);
  render(<EditorialExternalIngress {...props} />);
  const token = "controlled-source-token-12345678";
  expect(token).toHaveLength(32);
  fireEvent.change(screen.getByLabelText("来源专属令牌"), {
    target: { value: token.slice(0, -1) },
  });
  fireEvent.change(screen.getByLabelText("材料 JSON 数组"), {
    target: { value: '[{"identity_key":"one"}]' },
  });
  const submit = screen.getByRole("button", { name: "受理材料摄入" });
  expect((submit as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(submit);
  expect(api.submit).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("来源专属令牌"), {
    target: { value: token },
  });
  expect((submit as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(submit);
  await screen.findByText(/等待处理/);
  expect(api.submit.mock.calls[0][2].headers["X-HotKey-Source-Token"]).toBe(
    token,
  );
});

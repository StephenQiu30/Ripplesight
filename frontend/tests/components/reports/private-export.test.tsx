// @vitest-environment happy-dom
import { Blob as NodeBlob } from "node:buffer";
import { createHash, webcrypto } from "node:crypto";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const notices = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
const api = vi.hoisted(() => ({
  create: vi.fn(),
  read: vi.fn(),
  download: vi.fn(),
  cancel: vi.fn(),
  retry: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: notices }));
vi.mock("@/api/siyoudaochu", () => ({
  createReportExport: api.create,
  createContentExport: api.create,
  getReportExport: api.read,
  getContentExport: api.read,
  downloadReportExport: api.download,
  downloadContentExport: api.download,
}));
vi.mock("@/api/caijirenwu", () => ({
  cancelCollectionJob: api.cancel,
  retryCollectionJob: api.retry,
}));
import { PrivateExport } from "@/components/reports/private-export";

const body = "# 中文固定报告\n引用 https://example.invalid/fixed\n";
function receipt(
  status: HotKeyAPI.ExportView["status"] = "succeeded",
): HotKeyAPI.ExportView {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    kind: "report",
    job_id: "00000000-0000-4000-8000-000000000002",
    format: "markdown",
    renderer_version: "fixed-renderer",
    schema_version: "fixed-schema",
    status,
    content_count: 1,
    input_sha256: "1".repeat(64),
    artifact_sha256: createHash("sha256").update(body).digest("hex"),
    artifact_size: Buffer.byteLength(body),
    failure_code: null,
    created_at: "2026-10-04T00:00:00Z",
    updated_at: "2026-10-04T00:00:00Z",
  };
}
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("reuses one operation after an uncertain acceptance response and downloads only bytes matching the receipt", async () => {
  vi.stubGlobal("Blob", NodeBlob);
  vi.stubGlobal("crypto", webcrypto);
  const create = vi
    .spyOn(URL, "createObjectURL")
    .mockReturnValue("blob:private-export");
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
    () => undefined,
  );
  api.create
    .mockRejectedValueOnce(new Error("network response unknown"))
    .mockResolvedValueOnce(receipt());
  api.download.mockResolvedValue(
    new NodeBlob([body], { type: "text/markdown" }),
  );
  render(
    <PrivateExport
      target={{ kind: "report", reportId: "fixed-report", reportVersion: 7 }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "导出私有文件" }));
  await waitFor(() => expect(notices.error).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByRole("button", { name: "导出私有文件" }));
  const download = await screen.findByRole("button", { name: "下载文件" });
  expect(api.create.mock.calls[0][1].operation_id).toEqual(
    api.create.mock.calls[1][1].operation_id,
  );
  expect(api.create.mock.calls[1][1].report_version).toBe(7);
  fireEvent.click(download);
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  expect(api.download).toHaveBeenCalledWith(
    { export_id: receipt().id },
    expect.objectContaining({ responseType: "blob" }),
  );
});

it("rejects a changed file without creating a download object", async () => {
  vi.stubGlobal("Blob", NodeBlob);
  vi.stubGlobal("crypto", webcrypto);
  const create = vi.spyOn(URL, "createObjectURL");
  api.create.mockResolvedValue(receipt());
  api.download.mockResolvedValue(
    new NodeBlob(["changed private content"], { type: "text/markdown" }),
  );
  render(
    <PrivateExport
      target={{ kind: "report", reportId: "fixed-report", reportVersion: 7 }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "导出私有文件" }));
  fireEvent.click(await screen.findByRole("button", { name: "下载文件" }));
  await waitFor(() => expect(notices.error).toHaveBeenCalledOnce());
  expect(create).not.toHaveBeenCalled();
});

it("polls the accepted original job, stops on a read failure, and permits explicit status recovery", async () => {
  api.create.mockResolvedValue(receipt("pending"));
  api.read
    .mockRejectedValueOnce(new Error("state unavailable"))
    .mockResolvedValueOnce(receipt());
  render(
    <PrivateExport
      target={{ kind: "report", reportId: "fixed-report", reportVersion: 7 }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "导出私有文件" }));
  const recover = await screen.findByRole(
    "button",
    { name: "重新读取状态" },
    { timeout: 3500 },
  );
  expect(api.read).toHaveBeenCalledOnce();
  fireEvent.click(recover);
  await screen.findByRole("button", { name: "下载文件" }, { timeout: 3500 });
  expect(api.read).toHaveBeenCalledTimes(2);
  expect(api.cancel).not.toHaveBeenCalled();
  expect(api.retry).not.toHaveBeenCalled();
});

it("requires an explicit new acceptance after cancellation and keeps its operation on uncertain response", async () => {
  api.create
    .mockResolvedValueOnce({
      ...receipt("failed"),
      failure_code: "export_cancelled",
    })
    .mockRejectedValueOnce(new Error("new acceptance response unknown"))
    .mockResolvedValueOnce(receipt("pending"));
  render(
    <PrivateExport
      target={{ kind: "report", reportId: "fixed-report", reportVersion: 7 }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "导出私有文件" }));
  await screen.findByText("导出任务已取消");
  expect(screen.queryByRole("button", { name: "重试原任务" })).toBeNull();
  expect(api.create).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "重新受理" }));
  await waitFor(() => expect(notices.error).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByRole("button", { name: "重新受理" }));
  await screen.findByText("导出任务排队中");
  expect(api.create.mock.calls[1][1].operation_id).not.toBe(
    api.create.mock.calls[0][1].operation_id,
  );
  expect(api.create.mock.calls[2][1].operation_id).toBe(
    api.create.mock.calls[1][1].operation_id,
  );
  expect(api.create.mock.calls[2][1].report_version).toBe(7);
  expect(api.retry).not.toHaveBeenCalled();
});

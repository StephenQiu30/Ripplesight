import { selectOption } from "../../../../select";
// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  correctEditorialRun,
  getCurrentEditorialRun,
  requestEditorialRun,
} from "@/api/bianjifenxi";
import { EditorialCorrectionManager } from "@/app/publication/manage/components/editorial-correction-manager";

vi.mock("@/api/bianjifenxi", () => ({
  correctEditorialRun: vi.fn(),
  getCurrentEditorialRun: vi.fn(),
  requestEditorialRun: vi.fn(),
}));
const run = {
  id: "00000000-0000-4000-8000-000000000010",
  content_id: "00000000-0000-4000-8000-000000000011",
  content_version_id: "00000000-0000-4000-8000-000000000012",
  source_key: "test",
  source_revision: 1,
  prompt_version: "controlled",
  manual_version: 3,
  status: "complete",
  job_id: null,
  failure_code: null,
  created_at: "2026-10-02T00:00:00Z",
  updated_at: "2026-10-02T00:00:00Z",
  result: {
    relevance: "pass",
    selected: true,
    manual: true,
    silent: true,
    scores: [],
    manual_overrides: { silent: true },
  },
} satisfies HotKeyAPI.EditorialRunView;

afterEach(cleanup);

async function read() {
  fireEvent.change(screen.getByLabelText("操作员令牌"), {
    target: { value: "controlled-token" },
  });
  fireEvent.click(screen.getByRole("button", { name: "读取当前分析" }));
  await screen.findByText(/人工版本 3/);
}

beforeEach(() => {
  vi.mocked(getCurrentEditorialRun).mockReset().mockResolvedValue(run);
  vi.mocked(requestEditorialRun)
    .mockReset()
    .mockResolvedValue({
      ...run,
      status: "queued",
      result: null,
      job_id: "new-original-job",
    });
  vi.mocked(correctEditorialRun)
    .mockReset()
    .mockResolvedValue({ ...run, manual_version: 4 });
});

describe("editorial field correction", () => {
  it("sends only the changed false field with current version and operator headers", async () => {
    render(<EditorialCorrectionManager initialContentId={run.content_id} />);
    await read();
    await selectOption(screen.getByLabelText("精选操作"), "人工覆盖");
    await selectOption(screen.getByLabelText("精选"), "关闭");
    fireEvent.change(screen.getByLabelText("纠正原因"), {
      target: { value: "暂不精选" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存字段" }));
    await waitFor(() => expect(correctEditorialRun).toHaveBeenCalledOnce());
    expect(correctEditorialRun).toHaveBeenCalledWith(
      { run_id: run.id },
      {
        operation_id: expect.any(String),
        expected_manual_version: 3,
        action: "replace",
        reason: "暂不精选",
        selected: false,
        clear_fields: [],
      },
      {
        headers: {
          "X-HotKey-Operator-Token": "controlled-token",
          "X-HotKey-CSRF": "1",
        },
      },
    );
    await screen.findByText(/人工版本 4/);
  });

  it("restores all automatic evidence without also replacing any field", async () => {
    render(<EditorialCorrectionManager initialContentId={run.content_id} />);
    await read();
    await selectOption(screen.getByLabelText("静默推送操作"), "恢复自动");
    fireEvent.change(screen.getByLabelText("纠正原因"), {
      target: { value: "恢复自动" },
    });
    fireEvent.click(screen.getByRole("button", { name: "全部恢复自动结果" }));
    await waitFor(() => expect(correctEditorialRun).toHaveBeenCalledOnce());
    expect(vi.mocked(correctEditorialRun).mock.calls[0][1]).toEqual({
      operation_id: expect.any(String),
      expected_manual_version: 3,
      action: "clear",
      reason: "恢复自动",
    });
  });

  it("ignores a late result after the operator context is cleared", async () => {
    let resolve!: (value: HotKeyAPI.EditorialRunView) => void;
    vi.mocked(getCurrentEditorialRun).mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    render(<EditorialCorrectionManager initialContentId={run.content_id} />);
    fireEvent.change(screen.getByLabelText("操作员令牌"), {
      target: { value: "controlled-token" },
    });
    fireEvent.click(screen.getByRole("button", { name: "读取当前分析" }));
    fireEvent.click(screen.getByRole("button", { name: "清除令牌" }));
    resolve(run);
    await waitFor(() => expect(screen.queryByText(/人工版本 3/)).toBeNull());
    expect(
      (
        screen.getByRole("button", {
          name: "读取当前分析",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(correctEditorialRun).not.toHaveBeenCalled();
  });
});

it("enqueues a fresh full run using the displayed fixed version and preserves opid after an ambiguous response", async () => {
  vi.mocked(requestEditorialRun).mockRejectedValueOnce(new Error("offline"));
  render(<EditorialCorrectionManager initialContentId={run.content_id} />);
  await read();
  fireEvent.click(screen.getByRole("button", { name: "重新分析全部阶段" }));
  await waitFor(() => expect(requestEditorialRun).toHaveBeenCalledTimes(1));
  await screen.findByText("操作未完成，请重新读取后检查。");
  fireEvent.click(screen.getByRole("button", { name: "重新分析全部阶段" }));
  await waitFor(() => expect(requestEditorialRun).toHaveBeenCalledTimes(2));
  const first = vi.mocked(requestEditorialRun).mock.calls[0];
  expect(first).toEqual([
    { content_id: run.content_id, source_key: "test" },
    {
      operation_id: expect.any(String),
      content_version_id: run.content_version_id,
      expected_manual_version: 3,
      stages: "all",
    },
    {
      headers: {
        "X-HotKey-Operator-Token": "controlled-token",
        "X-HotKey-CSRF": "1",
      },
    },
  ]);
  expect(vi.mocked(requestEditorialRun).mock.calls[1]).toEqual(first);
  await screen.findByText(/已排队/);
  expect(
    screen.getByRole("link", { name: "查看分析任务" }).getAttribute("href"),
  ).toBe("/jobs/new-original-job");
});

it("separates public recommendation copy from private correction reason", async () => {
  render(<EditorialCorrectionManager initialContentId={run.content_id} />);
  await read();
  await selectOption(screen.getByLabelText("分类操作"), "人工覆盖");
  await selectOption(screen.getByLabelText("分类"), "论文");
  await selectOption(screen.getByLabelText("公开推荐理由操作"), "人工覆盖");
  fireEvent.change(screen.getByLabelText("公开推荐理由"), {
    target: { value: "公开说明" },
  });
  fireEvent.change(screen.getByLabelText("纠正原因"), {
    target: { value: "私有审计说明" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存字段" }));
  await waitFor(() => expect(correctEditorialRun).toHaveBeenCalledOnce());
  expect(vi.mocked(correctEditorialRun).mock.calls[0][1]).toMatchObject({
    category: "paper",
    reason_zh: "公开说明",
    reason: "私有审计说明",
  });
});

// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/api/caijirenwu", () => ({ getCollectionJob: api.get }));
import { JobCollectionCounts } from "@/components/collection/job-collection-counts";
import { ApiRequestError } from "@/request";

const counts: HotKeyAPI.JobCollectionCountsView = {
  identity_count_basis: "frozen_receipt_identity_v2",
  observed_count: 8,
  stored_observation_count: 5,
  unique_content_count: 4,
  inserted_count: 1,
  updated_count: 1,
  unchanged_count: 1,
  unclassified_count: 1,
};
const execution: HotKeyAPI.JobCollectionExecutionView = {
  execution_epoch: 2,
  collection_cycle_no: 1,
  started_at: "2026-10-12T00:00:00Z",
  finished_at: "2026-10-12T00:00:01Z",
  outcome: "failed",
  counts,
};
const receipt = {
  id: "job-a",
  kind: "keyword.search",
  collection_counts: {
    ...counts,
    inserted_count: 4,
    updated_count: 0,
    unchanged_count: 0,
    unclassified_count: 0,
  },
  collection_executions: [
    execution,
    {
      ...execution,
      execution_epoch: 1,
      counts: {
        ...counts,
        unique_content_count: 3,
        inserted_count: 3,
        updated_count: 0,
        unchanged_count: 0,
        unclassified_count: 0,
      },
    },
  ],
  collection_executions_has_more: true,
};
function expand(name = "查看累计与逐轮计量") {
  fireEvent.click(screen.getByRole("button", { name }));
}
function failure(status: number) {
  return new ApiRequestError({
    kind: "http",
    status,
    code: "denied",
    message: "受控错误",
  });
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("reads one receipt for cumulative and execution scopes without subtracting totals", async () => {
  api.get.mockResolvedValue(receipt);
  render(<JobCollectionCounts jobId="job-a" kind="keyword.search" />);
  expect(api.get).not.toHaveBeenCalled();
  expand();
  const rounds = await screen.findByRole("region", { name: "单轮执行差分" });
  const cumulative = within(
    screen.getByRole("region", { name: "任务计量" }),
  ).getAllByRole("region", { name: "采集计量" })[0];
  expect(within(cumulative).getByText("4 个身份")).toBeTruthy();
  expect(within(rounds).getAllByText("1 个身份")).toHaveLength(4);
  expect(within(rounds).getAllByText("分母：4 个唯一身份")).toHaveLength(4);
  expect(api.get).toHaveBeenCalledOnce();
  expect(screen.getByText(/仅展示最近 20 执行轮/)).toBeTruthy();
  fireEvent.click(within(rounds).getByRole("button", { name: /第 1 执行轮/ }));
  expect(within(rounds).getAllByText("分母：3 个唯一身份")).toHaveLength(4);
  expect(
    screen.getAllByRole("heading", { level: 6, name: "采集计量" }),
  ).toHaveLength(2);
});
it.each(["keyword.search", "source.comments"])(
  "resolves an unknown linked type from the %s receipt without showing cumulative counts",
  async (kind) => {
    api.get.mockResolvedValue({ ...receipt, kind });
    render(<JobCollectionCounts jobId="job-a" scope="execution" />);
    expand("查看逐轮摘要");
    const panel = await screen.findByRole("region", { name: "单轮执行差分" });
    expect(within(panel).getAllByText("1 个身份")).toHaveLength(4);
    expect(screen.queryByText("4 个身份")).toBeNull();
    expect(
      screen.getByText(/不是当前覆盖窗口、主题整轮或单份材料的独立增量/),
    ).toBeTruthy();
    expect(api.get).toHaveBeenCalledOnce();
  },
);
it("keeps other linked task kinds inapplicable and does not infer zero rounds", async () => {
  api.get.mockResolvedValue({ ...receipt, kind: "source.hotlist" });
  render(<JobCollectionCounts jobId="job-a" scope="execution" />);
  expand("查看逐轮摘要");
  await screen.findByText(/该任务类型不提供关键词\/评论单轮计量/);
  expect(screen.queryByRole("region", { name: "单轮执行差分" })).toBeNull();
  expect(screen.queryByText("0 个身份")).toBeNull();
});
it.each([null, undefined, []])(
  "keeps missing and not-yet-acquired execution histories distinct (%s)",
  async (collection_executions) => {
    api.get.mockResolvedValue({
      ...receipt,
      collection_executions,
      collection_executions_has_more: false,
    });
    render(<JobCollectionCounts jobId="job-a" scope="execution" />);
    expand("查看逐轮摘要");
    await screen.findByText(
      collection_executions == null ? /执行轮次记录未知/ : /尚无实际领取记录/,
    );
    expect(screen.queryByRole("region", { name: "采集计量" })).toBeNull();
  },
);
it("keeps an unattributed attempt unknown despite populated cumulative counts", async () => {
  api.get.mockResolvedValue({
    ...receipt,
    collection_executions: [{ ...execution, counts: null }],
  });
  render(<JobCollectionCounts jobId="job-a" scope="execution" />);
  expand("查看逐轮摘要");
  await screen.findByText(/本轮缺少可靠归属/);
  expect(screen.queryByText("4 个身份")).toBeNull();
});
it.each([401, 403, 404])(
  "clears cumulative and round receipts after refresh status %s",
  async (status) => {
    api.get
      .mockResolvedValueOnce(receipt)
      .mockRejectedValueOnce(failure(status));
    render(<JobCollectionCounts jobId="job-a" kind="keyword.search" />);
    expand();
    await screen.findByRole("region", { name: "单轮执行差分" });
    fireEvent.click(screen.getByRole("button", { name: "刷新计量" }));
    await screen.findByRole("alert");
    expect(screen.queryByRole("region", { name: "单轮执行差分" })).toBeNull();
    expect(screen.queryByRole("region", { name: "采集计量" })).toBeNull();
  },
);
it.each([{ id: "wrong-job" }, { kind: "source.comments" }])(
  "clears both scopes after a mismatched refresh (%s)",
  async (mismatch) => {
    api.get
      .mockResolvedValueOnce(receipt)
      .mockResolvedValueOnce({ ...receipt, ...mismatch });
    render(<JobCollectionCounts jobId="job-a" kind="keyword.search" />);
    expand();
    await screen.findByRole("region", { name: "单轮执行差分" });
    fireEvent.click(screen.getByRole("button", { name: "刷新计量" }));
    await screen.findByText("任务计量不存在或暂不可读");
    expect(screen.queryByRole("region", { name: "单轮执行差分" })).toBeNull();
    expect(screen.queryByRole("region", { name: "采集计量" })).toBeNull();
  },
);
it("retains both scopes during transient failure, then refreshes the actual next receipt", async () => {
  api.get
    .mockResolvedValueOnce(receipt)
    .mockRejectedValueOnce(failure(503))
    .mockResolvedValueOnce({ ...receipt, collection_executions: [] });
  render(<JobCollectionCounts jobId="job-a" kind="keyword.search" />);
  expand();
  await screen.findByRole("region", { name: "单轮执行差分" });
  fireEvent.click(screen.getByRole("button", { name: "刷新计量" }));
  await screen.findByText("计量刷新失败，已显示内容可能过期");
  expect(screen.getAllByRole("region", { name: "采集计量" })).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "重试计量" }));
  await screen.findByText(/尚无实际领取记录/);
  expect(screen.queryByText(/第 2 执行轮/)).toBeNull();
});
it("aborts a closed disclosure and ignores its delayed round receipt after reopening", async () => {
  const pending = deferred<typeof receipt>();
  api.get
    .mockReturnValueOnce(pending.promise)
    .mockResolvedValueOnce({ ...receipt, collection_executions: [] });
  render(<JobCollectionCounts jobId="job-a" scope="execution" />);
  expand("查看逐轮摘要");
  const signal: AbortSignal = api.get.mock.calls[0][1].signal;
  fireEvent.click(screen.getByRole("button", { name: "收起逐轮摘要" }));
  expect(signal.aborted).toBe(true);
  expand("查看逐轮摘要");
  await screen.findByText(/尚无实际领取记录/);
  pending.resolve(receipt);
  await waitFor(() => expect(screen.queryByText(/第 2 执行轮/)).toBeNull());
  expect(api.get).toHaveBeenCalledTimes(2);
});
it("clears the visible scope when the reference changes and ignores the old request", async () => {
  const pending = deferred<typeof receipt>();
  api.get.mockReturnValueOnce(pending.promise).mockResolvedValueOnce({
    ...receipt,
    id: "job-b",
    collection_executions: [],
  });
  const view = render(<JobCollectionCounts jobId="job-a" scope="execution" />);
  expand("查看逐轮摘要");
  const signal: AbortSignal = api.get.mock.calls[0][1].signal;
  view.rerender(<JobCollectionCounts jobId="job-b" scope="execution" />);
  expect(signal.aborted).toBe(true);
  await screen.findByText(/尚无实际领取记录/);
  pending.resolve(receipt);
  await waitFor(() => expect(screen.queryByText(/第 2 执行轮/)).toBeNull());
  expect(screen.getByText("关联任务：job-b")).toBeTruthy();
});

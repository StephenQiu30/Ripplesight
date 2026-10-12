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

const counts = {
  identity_count_basis: "frozen_receipt_identity_v2",
  observed_count: 12,
  stored_observation_count: 9,
  unique_content_count: 4,
  inserted_count: 1,
  updated_count: 1,
  unchanged_count: 1,
  unclassified_count: 1,
};
const receipt = {
  id: "job-a",
  kind: "keyword.search",
  collection_counts: counts,
};
function show() {
  return render(<JobCollectionCounts jobId="job-a" kind="keyword.search" />);
}
function expand() {
  fireEvent.click(screen.getByRole("button", { name: "查看累计与逐轮计量" }));
}
function error(status: number) {
  return new ApiRequestError({
    kind: "http",
    status,
    code: "permission_denied",
    message: "拒绝",
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

it.each(["keyword.search", "source.comments"] as const)(
  "reads %s only after explicit expansion and shows independent denominators",
  async (kind) => {
    api.get.mockResolvedValue({ ...receipt, kind });
    render(<JobCollectionCounts jobId="job-a" kind={kind} />);
    expect(api.get).not.toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: "任务计量" })).toBeNull();
    expand();
    const panel = await screen.findByRole("region", { name: "采集计量" });
    expect(api.get).toHaveBeenCalledOnce();
    expect(api.get.mock.calls[0][0]).toEqual({ job_id: "job-a" });
    expect(screen.getByText(/包含全部重试/)).toBeTruthy();
    expect(within(panel).getByText("12 条")).toBeTruthy();
    expect(within(panel).getByText("9 条")).toBeTruthy();
    expect(within(panel).getByText("4 个唯一身份")).toBeTruthy();
    expect(within(panel).getAllByText("1 个身份")).toHaveLength(4);
    expect(within(panel).getAllByText("分母：4 个唯一身份")).toHaveLength(4);
    expect(within(panel).queryByText("旧口径重复观察")).toBeNull();
  },
);

it("keeps unknown upstream count separate from known zero stored identities", async () => {
  api.get.mockResolvedValue({
    ...receipt,
    collection_counts: {
      ...counts,
      observed_count: null,
      stored_observation_count: 0,
      unique_content_count: 0,
      inserted_count: 0,
      updated_count: 0,
      unchanged_count: 0,
      unclassified_count: 0,
    },
  });
  show();
  expand();
  const panel = await screen.findByRole("region", { name: "采集计量" });
  expect(within(panel).getByText("未知")).toBeTruthy();
  expect(within(panel).getAllByText("0 个身份")).toHaveLength(4);
  expect(within(panel).getAllByText("分母：0 个唯一身份")).toHaveLength(4);
});

it.each([null, undefined])(
  "preserves absent legacy counting fields as unknown (%s)",
  async (collection_counts) => {
    api.get.mockResolvedValue({
      ...receipt,
      collection_counts,
      progress: { items_saved: 90 },
    });
    show();
    expand();
    const panel = await screen.findByRole("region", { name: "采集计量" });
    expect(within(panel).getByText(/未提供可核对的身份计量口径/)).toBeTruthy();
    expect(within(panel).getAllByText("未知")).toHaveLength(7);
    expect(within(panel).getAllByText("分母：未知")).toHaveLength(4);
    expect(panel.textContent).not.toContain("90");
    expect(panel.textContent).not.toContain("0 个身份");
  },
);

it("does not interpret a future counting basis as a known classification", async () => {
  api.get.mockResolvedValue({
    ...receipt,
    collection_counts: { ...counts, identity_count_basis: "future" },
  });
  show();
  expand();
  const panel = await screen.findByRole("region", { name: "采集计量" });
  expect(within(panel).queryByText("1 个身份")).toBeNull();
  expect(within(panel).getAllByText("分母：未知")).toHaveLength(4);
});

it("shows loading without fabricated counts", async () => {
  const pending = deferred<typeof receipt>();
  api.get.mockReturnValue(pending.promise);
  show();
  expand();
  await screen.findByText("正在读取任务计量。");
  expect(screen.queryByRole("region", { name: "采集计量" })).toBeNull();
  pending.resolve(receipt);
  await screen.findByRole("region", { name: "采集计量" });
});

it("retries an initial failure without writing or inventing zero", async () => {
  api.get
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce(receipt);
  show();
  expand();
  await screen.findByText("无法读取任务计量");
  expect(screen.queryByRole("region", { name: "采集计量" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重试计量" }));
  await screen.findByRole("region", { name: "采集计量" });
  expect(api.get).toHaveBeenCalledTimes(2);
});

it("preserves the prior receipt during refresh and marks transient failure stale", async () => {
  const pending = deferred<typeof receipt>();
  api.get
    .mockResolvedValueOnce(receipt)
    .mockReturnValueOnce(pending.promise)
    .mockRejectedValueOnce(new Error("offline"));
  show();
  expand();
  await screen.findByRole("region", { name: "采集计量" });
  fireEvent.click(screen.getByRole("button", { name: "刷新计量" }));
  await screen.findByText("正在刷新，暂时显示上次计量。");
  expect(screen.getAllByText("1 个身份")).toHaveLength(4);
  pending.resolve(receipt);
  await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
  fireEvent.click(screen.getByRole("button", { name: "刷新计量" }));
  await screen.findByText("计量刷新失败，已显示内容可能过期");
  expect(screen.getAllByText("1 个身份")).toHaveLength(4);
});

it.each([401, 403, 404])(
  "removes the old receipt after refresh becomes inaccessible (%s)",
  async (status) => {
    api.get.mockResolvedValueOnce(receipt).mockRejectedValueOnce(error(status));
    show();
    expand();
    await screen.findByRole("region", { name: "采集计量" });
    fireEvent.click(screen.getByRole("button", { name: "刷新计量" }));
    await screen.findByText(
      status === 404 ? "任务计量不存在或暂不可读" : "暂时无法访问任务计量",
    );
    expect(screen.queryByRole("region", { name: "采集计量" })).toBeNull();
    expect(screen.queryByText("1 个身份")).toBeNull();
  },
);

it.each([401, 403, 404])(
  "does not display counts on initial permission or missing failure (%s)",
  async (status) => {
    api.get.mockRejectedValue(error(status));
    show();
    expand();
    await screen.findByText(
      status === 404 ? "任务计量不存在或暂不可读" : "暂时无法访问任务计量",
    );
    expect(screen.queryByRole("region", { name: "采集计量" })).toBeNull();
  },
);

it("aborts on close and ignores the old late result when reopened", async () => {
  const pending = deferred<typeof receipt>();
  api.get.mockReturnValueOnce(pending.promise).mockResolvedValueOnce({
    ...receipt,
    collection_counts: { ...counts, observed_count: 27 },
  });
  show();
  expand();
  await screen.findByText("正在读取任务计量。");
  const signal = api.get.mock.calls[0][1].signal as AbortSignal;
  fireEvent.click(screen.getByRole("button", { name: "收起累计与逐轮计量" }));
  expect(signal.aborted).toBe(true);
  expand();
  await screen.findByText("27 条");
  pending.resolve(receipt);
  await Promise.resolve();
  expect(screen.queryByText("12 条")).toBeNull();
  expect(screen.getByText("27 条")).toBeTruthy();
});

it("aborts on unmount", async () => {
  api.get.mockReturnValue(new Promise(() => {}));
  const view = show();
  expand();
  await screen.findByText("正在读取任务计量。");
  const signal = api.get.mock.calls[0][1].signal as AbortSignal;
  view.unmount();
  expect(signal.aborted).toBe(true);
});

it("isolates a changed task from the old late response", async () => {
  const pending = deferred<typeof receipt>();
  api.get.mockReturnValueOnce(pending.promise).mockResolvedValueOnce({
    ...receipt,
    id: "job-b",
    collection_counts: { ...counts, observed_count: 27 },
  });
  const view = show();
  expand();
  await screen.findByText("正在读取任务计量。");
  const signal = api.get.mock.calls[0][1].signal as AbortSignal;
  view.rerender(<JobCollectionCounts jobId="job-b" kind="keyword.search" />);
  await screen.findByText("27 条");
  expect(signal.aborted).toBe(true);
  pending.resolve(receipt);
  await Promise.resolve();
  expect(screen.queryByText("12 条")).toBeNull();
});

it.each([
  { ...receipt, id: "job-b" },
  { ...receipt, kind: "source.hotlist" },
])("refuses a mismatched task receipt", async (response) => {
  api.get.mockResolvedValue(response);
  show();
  expand();
  await screen.findByText("任务计量不存在或暂不可读");
  expect(screen.queryByRole("region", { name: "采集计量" })).toBeNull();
});

it("keeps multiple cards independent and reads only the explicitly opened card", async () => {
  api.get.mockImplementation(({ job_id }: { job_id: string }) =>
    Promise.resolve({ ...receipt, id: job_id }),
  );
  render(
    <>
      <JobCollectionCounts jobId="job-a" kind="keyword.search" />
      <JobCollectionCounts jobId="job-b" kind="keyword.search" />
    </>,
  );
  fireEvent.click(
    screen.getAllByRole("button", { name: "查看累计与逐轮计量" })[1],
  );
  await screen.findByRole("region", { name: "采集计量" });
  expect(api.get).toHaveBeenCalledOnce();
  expect(api.get.mock.calls[0][0]).toEqual({ job_id: "job-b" });
  expect(screen.getAllByRole("region", { name: "任务计量" })).toHaveLength(1);
});

// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  act,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/request";
const mocks = vi.hoisted(() => ({
  content: vi.fn(),
  sources: vi.fn(),
  history: vi.fn(),
  detail: vi.fn(),
  editions: vi.fn(),
  requestEdition: vi.fn(),
  replace: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/api/zuopinziliao", () => ({ getContentRecord: mocks.content }));
vi.mock("@/api/rebang", () => ({
  listHotlistSources: mocks.sources,
  listHotlistSnapshots: mocks.history,
  getHistoricalHotlistSnapshot: mocks.detail,
}));
vi.mock("@/api/rizhouyuekan", () => ({
  listReportEditions: mocks.editions,
  requestReportEdition: mocks.requestEdition,
}));
import { ContentDetail } from "@/app/content/[contentId]/components/content-detail";
import { HotlistWorkspace } from "@/app/hotlists/components/hotlist-workspace";
import { EditionList } from "@/app/editions/components/edition-list";
const denied = (status: number) =>
  new ApiRequestError({
    kind: "http",
    status,
    code: "permission_denied",
    message: "denied",
  });
afterEach(cleanup);
beforeEach(() => vi.resetAllMocks());
it.each([401, 403])(
  "distinguishes private first-read denial %s from retryable errors",
  async (status) => {
    mocks.content.mockRejectedValue(denied(status));
    const content = render(<ContentDetail contentId="private-id" />);
    await screen.findByRole("heading", { name: "无权读取作品" });
    expect(
      screen.queryByRole("heading", { name: "暂时无法读取作品" }),
    ).toBeNull();
    content.unmount();
    mocks.sources.mockRejectedValue(denied(status));
    const hotlist = render(<HotlistWorkspace />);
    await screen.findByRole("heading", { name: "无权读取热榜" });
    hotlist.unmount();
    mocks.editions.mockRejectedValue(denied(status));
    render(<EditionList />);
    await screen.findByText("无权读取刊期");
    expect(
      (screen.getByRole("button", { name: "提交编选" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(mocks.requestEdition).not.toHaveBeenCalled();
  },
);
const snapshot: HotKeyAPI.HotlistSnapshotView = {
  snapshot_id: "snapshot-1",
  source_key: "hotlist_weibo",
  observed_at: "2026-10-08T00:00:00Z",
  due_at: "2026-10-08T00:00:00Z",
  operation_id: "op-1",
  entry_count: 1,
  previous_snapshot_id: null,
  gap_count: 0,
  next_cursor: 1,
  items: [
    {
      rank: 1,
      title: "私有榜位标题",
      url: "https://example.test/private",
      summary: null,
      heat: null,
      published_at: null,
      content_id: null,
      previous_rank: null,
      rank_delta: null,
      rank_change: "new",
      matched: false,
      matched_topic_names: [],
    },
  ],
};
it.each([401, 403, 503])(
  "handles history pagination failure %s without retaining revoked private rows",
  async (status) => {
    mocks.sources.mockResolvedValue({
      items: [{ source_key: "hotlist_weibo" }],
    });
    mocks.history
      .mockResolvedValueOnce({ items: [snapshot], next_cursor: "next" })
      .mockRejectedValue(denied(status));
    mocks.detail.mockResolvedValue(snapshot);
    render(<HotlistWorkspace />);
    await screen.findByRole("heading", { name: "私有榜位标题" });
    fireEvent.click(screen.getByRole("button", { name: "更多时间" }));
    if (status === 503) {
      await screen.findByRole("button", { name: "更多时间" });
      expect(
        screen.getByRole("heading", { name: "私有榜位标题" }),
      ).toBeTruthy();
    } else {
      await screen.findByText("无权读取历史快照");
      expect(
        screen.queryByRole("heading", { name: "私有榜位标题" }),
      ).toBeNull();
      expect(screen.queryByRole("combobox", { name: "观察时间" })).toBeNull();
    }
  },
);
it.each([401, 403, 503])(
  "handles entry pagination failure %s without retaining revoked private rows",
  async (status) => {
    mocks.sources.mockResolvedValue({
      items: [{ source_key: "hotlist_weibo" }],
    });
    mocks.history.mockResolvedValue({ items: [snapshot], next_cursor: null });
    mocks.detail
      .mockResolvedValueOnce(snapshot)
      .mockRejectedValue(denied(status));
    render(<HotlistWorkspace />);
    await screen.findByRole("heading", { name: "私有榜位标题" });
    fireEvent.click(screen.getByRole("button", { name: "加载更多榜位" }));
    if (status === 503) {
      await screen.findByRole("button", { name: "加载更多榜位" });
      expect(
        screen.getByRole("heading", { name: "私有榜位标题" }),
      ).toBeTruthy();
    } else {
      await screen.findByText("快照不存在或无权访问");
      expect(
        screen.queryByRole("heading", { name: "私有榜位标题" }),
      ).toBeNull();
    }
  },
);

it("ignores an accepted edition response after list refresh denies access", async () => {
  let complete: (value: HotKeyAPI.EditionDetailView) => void = () => {};
  mocks.editions.mockResolvedValueOnce([]).mockRejectedValueOnce(denied(403));
  mocks.requestEdition.mockImplementationOnce(
    () =>
      new Promise<HotKeyAPI.EditionDetailView>((resolve) => {
        complete = resolve;
      }),
  );
  render(<EditionList />);
  await screen.findByText("暂无日报刊期。");
  fireEvent.change(screen.getByLabelText("刊期"), {
    target: { value: "2026-10-01" },
  });
  fireEvent.change(screen.getByLabelText("编选原因"), {
    target: { value: "验收" },
  });
  fireEvent.submit(
    screen.getByRole("button", { name: "提交编选" }).closest("form")!,
  );
  expect(mocks.requestEdition).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "刷新" }));
  await screen.findByText("无权读取刊期");
  await act(async () => {
    complete({ id: "private-edition" } as HotKeyAPI.EditionDetailView);
  });
  expect(screen.queryByRole("link", { name: "查看进度与正文" })).toBeNull();
  expect(mocks.editions).toHaveBeenCalledTimes(2);
  fireEvent.submit(
    screen.getByRole("button", { name: "提交编选" }).closest("form")!,
  );
  expect(mocks.requestEdition).toHaveBeenCalledOnce();
});

it("keeps edition submissions disabled through denial then outage until a lawful read succeeds", async () => {
  mocks.editions
    .mockRejectedValueOnce(denied(403))
    .mockRejectedValueOnce(denied(503))
    .mockResolvedValueOnce([]);
  render(<EditionList />);
  await screen.findByText("无权读取刊期");
  fireEvent.click(screen.getByRole("button", { name: "刷新" }));
  await act(async () => {
    await Promise.resolve();
  });
  expect(mocks.editions).toHaveBeenCalledTimes(2);
  expect(
    (screen.getByRole("button", { name: "提交编选" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  fireEvent.submit(
    screen.getByRole("button", { name: "提交编选" }).closest("form")!,
  );
  expect(mocks.requestEdition).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "刷新" }));
  await screen.findByText("暂无日报刊期。");
  expect(
    (screen.getByRole("button", { name: "提交编选" }) as HTMLButtonElement)
      .disabled,
  ).toBe(false);
});

it("announces the edition archive wait and ends it after a successful read", async () => {
  let complete: (value: HotKeyAPI.EditionSummaryView[]) => void = () => {};
  mocks.editions.mockImplementationOnce(
    () =>
      new Promise<HotKeyAPI.EditionSummaryView[]>((resolve) => {
        complete = resolve;
      }),
  );
  render(<EditionList />);
  expect(
    screen
      .getByRole("status", { name: "正在读取刊期档案" })
      .getAttribute("aria-busy"),
  ).toBe("true");
  await act(async () => {
    complete([]);
  });
  await screen.findByText("暂无日报刊期。");
  expect(screen.queryByRole("status", { name: "正在读取刊期档案" })).toBeNull();
});

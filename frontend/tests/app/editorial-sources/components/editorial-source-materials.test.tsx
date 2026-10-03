// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/request";
import { EditorialSourceMaterials } from "@/app/editorial-sources/components/editorial-source-materials";
const notifications = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: notifications }));

const api = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("@/api/zuopinziliao", () => ({ listContentRecords: api.list }));
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);
const props = {
  token: "controlled",
  sourceKey: "ed_rss_one",
  name: "受控来源",
};
function item(id: string, title: string, state = "missing") {
  return {
    id,
    source_key: props.sourceKey,
    object_type: "webpage",
    analysis_state: state,
    timeline_at: null,
    current_visibility: null,
    latest_observation: {
      observed_at: "2026-10-02T01:00:00Z",
      published_at: null,
      content_version: { title, body: "已许可原材料正文", text_scope: "full" },
    },
  };
}
it("uses the exact profile source key and exposes unselected or failed original material through the existing reader", async () => {
  api.list.mockResolvedValue({
    items: [
      item("first", "未分析材料"),
      item("failed", "失败仍可读材料", "failed"),
    ],
    next_cursor: null,
  });
  render(<EditorialSourceMaterials {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "读取来源材料" }));
  await screen.findByText("失败仍可读材料");
  expect(api.list.mock.calls[0][0]).toEqual({
    source_key: "ed_rss_one",
    limit: 20,
  });
  expect(api.list.mock.calls[0][1].headers["X-HotKey-Operator-Token"]).toBe(
    "controlled",
  );
  expect(
    screen.getByRole("link", { name: "查看原材料 first" }).getAttribute("href"),
  ).toBe("/content/first");
  expect(
    screen
      .getByRole("link", { name: "编辑分析与发布 failed" })
      .getAttribute("href"),
  ).toBe("/publication/manage?content_id=failed");
  expect(screen.getByText(/标注失败/)).toBeTruthy();
});
it("follows an opaque cursor and keeps already loaded rows on a later-page failure", async () => {
  api.list
    .mockResolvedValueOnce({
      items: [item("first", "首条材料")],
      next_cursor: "opaque-position",
    })
    .mockRejectedValueOnce(new Error("temporary"))
    .mockResolvedValueOnce({
      items: [item("second", "后页材料")],
      next_cursor: null,
    });
  render(<EditorialSourceMaterials {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "读取来源材料" }));
  fireEvent.click(await screen.findByRole("button", { name: "读取更多材料" }));
  await waitFor(() =>
    expect(notifications.error).toHaveBeenCalledWith(
      expect.stringContaining("已加载材料保留"),
    ),
  );
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByText("首条材料")).toBeTruthy();
  expect(api.list.mock.calls[1][0]).toEqual({
    source_key: "ed_rss_one",
    limit: 20,
    cursor: "opaque-position",
  });
  fireEvent.click(screen.getByRole("button", { name: "读取更多材料" }));
  await screen.findByText("后页材料");
  expect(screen.getByText(/已加载 2 条/)).toBeTruthy();
});
it("makes no anonymous request and ignores a response after changing the source context", async () => {
  let complete!: (value: object) => void;
  api.list.mockImplementation(
    () =>
      new Promise((resolve) => {
        complete = resolve;
      }),
  );
  const view = render(
    <EditorialSourceMaterials key="closed" {...props} token="" />,
  );
  expect(
    (screen.getByRole("button", { name: "读取来源材料" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(api.list).not.toHaveBeenCalled();
  view.rerender(<EditorialSourceMaterials key="one" {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "读取来源材料" }));
  await waitFor(() => expect(api.list).toHaveBeenCalledTimes(1));
  view.rerender(
    <EditorialSourceMaterials
      key="two"
      {...props}
      sourceKey="ed_rss_two"
      name="另一个来源"
    />,
  );
  complete({ items: [item("old", "旧来源晚响应")], next_cursor: null });
  expect(screen.queryByText("旧来源晚响应")).toBeNull();
  expect(screen.getByText("另一个来源 · 原材料")).toBeTruthy();
});

it("silences a cancelled material read and restores the retry control", async () => {
  api.list.mockRejectedValue(
    new ApiRequestError({ kind: "cancelled", message: "读取已取消" }),
  );
  render(<EditorialSourceMaterials {...props} />);
  const read = screen.getByRole("button", { name: "读取来源材料" });
  fireEvent.click(read);
  await waitFor(() => expect((read as HTMLButtonElement).disabled).toBe(false));
  expect(api.list).toHaveBeenCalledOnce();
  expect(notifications.error).not.toHaveBeenCalled();
  expect(screen.queryByRole("alert")).toBeNull();
});

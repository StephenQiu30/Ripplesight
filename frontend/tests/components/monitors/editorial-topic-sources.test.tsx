// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ list: vi.fn(), error: vi.fn() }));
vi.mock("@/api/jiankongzhuti", () => ({
  listMonitorEditorialSources: api.list,
}));
vi.mock("sonner", () => ({ toast: { error: api.error } }));

import { EditorialTopicSources } from "@/components/monitors/editorial-topic-sources";

const source: HotKeyAPI.EditorialTopicSourceView = {
  profile_id: "approved-profile",
  source_key: "ed_rss_approved",
  name: "公开产品动态",
  configuration_version: 2,
  enabled: true,
  query_mode: "local_filter",
  text_scope: "summary",
  selectable: true,
  reason: null,
  last_ok_at: null,
  interval_minutes: 60,
};

beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

describe("personal topic subscription sources", () => {
  it("rejects a candidate selection while allowing removal of an unavailable selected source", async () => {
    api.list.mockResolvedValue([
      source,
      {
        ...source,
        profile_id: "candidate",
        name: "待验证来源",
        selectable: false,
        reason: "尚未准入",
      },
    ]);
    const changed = vi.fn();
    render(
      <EditorialTopicSources
        selectedProfileIds={["unavailable"]}
        onChange={changed}
        disabled={false}
      />,
    );
    await screen.findByLabelText("公开产品动态");
    expect(screen.getByRole("switch", { name: "公开产品动态" })).toBeTruthy();
    expect(
      (screen.getByLabelText("待验证来源") as HTMLInputElement).disabled,
    ).toBe(true);
    fireEvent.click(screen.getByLabelText("公开产品动态"));
    expect(changed).toHaveBeenLastCalledWith([
      "approved-profile",
      "unavailable",
    ]);
    fireEvent.click(screen.getByLabelText("当前不可用的订阅流"));
    expect(changed).toHaveBeenLastCalledWith([]);
    expect(screen.getAllByText(/每 60 分钟检查更新/)[0]?.textContent).toContain(
      "来源摘要",
    );
    expect(api.list).toHaveBeenCalledTimes(1);
  });

  it("keeps the selection on an API failure and retries only the read", async () => {
    api.list
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce([source]);
    const changed = vi.fn();
    render(
      <EditorialTopicSources
        selectedProfileIds={[source.profile_id]}
        onChange={changed}
        disabled={false}
      />,
    );
    await screen.findByText("订阅流暂时不可用");
    expect(changed).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "重新读取订阅流" }));
    await screen.findByLabelText("公开产品动态");
    expect(
      screen.getByLabelText("公开产品动态").getAttribute("aria-checked"),
    ).toBe("true");
    expect(api.list).toHaveBeenCalledTimes(2);
  });

  it("ignores a late response after the component leaves the page", async () => {
    let resolve!: (items: HotKeyAPI.EditorialTopicSourceView[]) => void;
    api.list.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    const changed = vi.fn();
    const view = render(
      <EditorialTopicSources
        selectedProfileIds={[]}
        onChange={changed}
        disabled={false}
      />,
    );
    view.unmount();
    resolve([source]);
    await waitFor(() => expect(changed).not.toHaveBeenCalled());
    expect(api.error).not.toHaveBeenCalled();
  });
});

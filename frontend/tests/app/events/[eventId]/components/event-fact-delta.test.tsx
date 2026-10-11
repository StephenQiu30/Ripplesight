// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { EventFactDelta } from "@/app/events/[eventId]/components/event-fact-delta";
import type { EventSource } from "@/components/events/reading-model";

afterEach(cleanup);
const changes: HotKeyAPI.EventMaterialChange[] = [
  {
    event_member_id: "m1",
    content_version_id: "v1",
    fact_id: "new",
    kind: "new_fact",
  },
  {
    event_member_id: "m2",
    content_version_id: "v2",
    fact_id: "new",
    kind: "new_fact",
  },
  {
    event_member_id: "m3",
    content_version_id: "v3",
    fact_id: "old",
    kind: "supplement",
    reason: "补充可核对证据",
  },
  {
    event_member_id: "m4",
    content_version_id: "v4",
    fact_id: "old",
    kind: "repeat",
    reason: "重复发布信息",
  },
  {
    event_member_id: "m5",
    content_version_id: "v5",
    fact_id: "old",
    kind: "unknown",
  },
];
const delta: HotKeyAPI.EventRevisionDeltaView = {
  version: "fact_delta_v1",
  event_id: "event",
  baseline_event_revision: 1,
  event_revision: 2,
  material_changes: changes,
  new_fact_count: 1,
  new_fact_material_count: 2,
  supplement_count: 1,
  repeat_count: 1,
  unknown_count: 1,
  material_count: 5,
};
const page: HotKeyAPI.EventFactPageView = {
  event_id: "event",
  event_revision: 2,
  facts: [],
  delta_state: "available",
  delta,
};
const sources: EventSource[] = changes.map((item, index) => ({
  id: item.event_member_id,
  number: index + 1,
  source: "controlled",
  title: "固定原文",
  time: null,
  href: null,
  originalUrl: null,
  availability: "pending",
}));
const renderPage = (value = page) =>
  render(<EventFactDelta page={value} sources={sources} />);

describe("automatic revision fact delta", () => {
  it("separates distinct facts from the exclusive new-material denominator", () => {
    renderPage();
    expect(screen.getByText(/新增事实/).textContent).toContain("新增事实 1 个");
    expect(screen.getByText(/新事实材料/).textContent).toContain("2 / 5");
    for (const label of ["补证", "重复转述", "未知"])
      expect(screen.getByText(new RegExp(`^${label} `)).textContent).toContain(
        "1 / 5",
      );
    expect(screen.getByText(/基准事件修订 1/).textContent).toContain(
      "事件修订 2",
    );
    expect(screen.getByText(/四类互斥/).textContent).toContain(
      "不含既有上下文",
    );
    expect(screen.getByText(/基准事件修订 1/).textContent).toContain(
      "不代表24小时变化",
    );
  });
  it("expands exact fixed-source anchors and judgments", () => {
    renderPage();
    const button = screen.getByRole("button", { name: "逐材料核对变化" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(
      screen.getByRole("link", { name: "变化来源 3" }).getAttribute("href"),
    ).toBe("#event-source-m3");
    expect(screen.getByText("补充可核对证据")).toBeTruthy();
    expect(screen.getByText("未保存可靠分类，保持未知。")).toBeTruthy();
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });
  it("labels the explicit empty baseline for an initial revision", () => {
    renderPage({
      ...page,
      event_revision: 1,
      delta: { ...delta, baseline_event_revision: 0, event_revision: 1 },
    });
    expect(screen.getByText(/首次成案，空基准修订 0/)).toBeTruthy();
  });
  it("keeps recorded zero facts different from missing history", () => {
    renderPage({
      ...page,
      delta: {
        ...delta,
        new_fact_count: 0,
        new_fact_material_count: 0,
        unknown_count: 3,
        material_changes: changes.map((item) =>
          item.kind === "new_fact" ? { ...item, kind: "unknown" } : item,
        ),
      },
    });
    expect(screen.getByText(/^新增事实/).textContent).toContain(
      "新增事实 0 个",
    );
    expect(screen.queryByText(/数量未知/)).toBeNull();
  });
  it.each(["not_recorded", "invalid", "ambiguous", undefined] as const)(
    "keeps %s receipts unknown",
    (delta_state) => {
      renderPage({ ...page, delta_state, delta: null });
      expect(screen.getByText(/数量未知/)).toBeTruthy();
      expect(screen.queryByText(/新增事实 0/)).toBeNull();
    },
  );
  it.each([
    { version: "future" },
    { event_revision: 3 },
    { event_id: "another" },
    { baseline_event_revision: -1 },
    { baseline_event_revision: 0.5 },
    { material_count: 6 },
    { new_fact_count: 2 },
    { new_fact_material_count: 1 },
    { supplement_count: -1 },
    { repeat_count: NaN },
    { unknown_count: Infinity },
    { material_changes: [] },
    { material_changes: [changes[0], changes[0]] },
  ])("keeps contradictory receipts unknown %j", (patch) => {
    renderPage({
      ...page,
      delta: { ...delta, ...patch } as HotKeyAPI.EventRevisionDeltaView,
    });
    expect(screen.getByText(/数量未知/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "逐材料核对变化" })).toBeNull();
  });
  it("hides withdrawn reasons while retaining the unknown denominator", () => {
    renderPage({
      ...page,
      delta: {
        ...delta,
        supplement_count: 0,
        unknown_count: 2,
        material_changes: changes.map((item) =>
          item.kind === "supplement"
            ? { ...item, kind: "unknown", reason: null, unavailable: true }
            : item,
        ),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "逐材料核对变化" }));
    expect(screen.getByText(/证据不可读或关联已变/)).toBeTruthy();
    expect(screen.queryByText("补充可核对证据")).toBeNull();
    expect(screen.getByText(/^未知 /).textContent).toContain("2 / 5");
  });
  it("does not invent sources for unloaded references", () => {
    render(<EventFactDelta page={page} sources={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "逐材料核对变化" }));
    expect(screen.getAllByText("固定来源待读取")).toHaveLength(5);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });
});

// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { EventEvidence } from "@/app/events/[eventId]/components/event-evidence";

afterEach(cleanup);

const receipt = {
  revision: 3,
  member_count: 1,
  readable_member_count: 1,
  evidence_state: "complete" as const,
  source_counts: { controlled: 1 },
};

describe("current event evidence scope", () => {
  it("labels one readable material as a clue with the revision and denominator", () => {
    render(<EventEvidence event={receipt} />);
    const section = screen.getByRole("region", {
      name: "当前事件的证据范围",
    });
    expect(section.textContent).toContain("单材料线索");
    expect(section.textContent).toContain("当前事件修订 3");
    expect(section.textContent).toContain("可读成员 1 / 此修订成员总数 1");
    expect(section.textContent).toContain("controlled 1 条");
    expect(section.textContent).toContain("不代表独立证实或新增事实数");
  });

  it.each([{ controlled: 2 }, { controlled: 1, other: 1 }])(
    "does not turn multiple materials or sources into independent confirmation: %j",
    (source_counts) => {
      render(
        <EventEvidence
          event={{
            ...receipt,
            member_count: 2,
            readable_member_count: 2,
            source_counts,
          }}
        />,
      );
      expect(screen.getByText("多材料关联")).toBeTruthy();
      expect(screen.queryByText("单材料线索")).toBeNull();
      expect(screen.getByText(/仍需结合原文核对/)).toBeTruthy();
      expect(screen.getByText(/可读成员 2 \/ 此修订成员总数 2/)).toBeTruthy();
    },
  );

  it("keeps the full denominator when only one of multiple members is readable", () => {
    render(
      <EventEvidence
        event={{ ...receipt, member_count: 3, evidence_state: "partial" }}
      />,
    );
    expect(screen.getByText("部分证据不可读")).toBeTruthy();
    expect(screen.queryByText("单材料线索")).toBeNull();
    expect(screen.getByText(/可读成员 1 \/ 此修订成员总数 3/)).toBeTruthy();
  });

  it.each([0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, undefined])(
    "keeps invalid or missing member count %s unknown",
    (member_count) => {
      render(<EventEvidence event={{ ...receipt, member_count }} />);
      expect(screen.getByText("证据范围待确定")).toBeTruthy();
      expect(
        screen.getByText(/可读成员 未知 \/ 此修订成员总数 未知/),
      ).toBeTruthy();
      expect(screen.queryByText("单材料线索")).toBeNull();
    },
  );

  it.each([
    { readable_member_count: 2 },
    { readable_member_count: 0 },
    { readable_member_count: undefined },
    { revision: undefined },
    { revision: 0 },
    { evidence_state: undefined },
    { evidence_state: "partial" as const },
    { member_count: 2 },
  ])("does not infer a scope from inconsistent receipts: %j", (patch) => {
    render(<EventEvidence event={{ ...receipt, ...patch }} />);
    expect(screen.getByText("证据范围待确定")).toBeTruthy();
    expect(screen.queryByText("单材料线索")).toBeNull();
    expect(screen.queryByText("多材料关联")).toBeNull();
  });

  it.each([
    undefined,
    {},
    { controlled: 2 },
    { controlled: 0, other: 1 },
    { controlled: -1, other: 2 },
    { controlled: 0.5, other: 0.5 },
    { " ": 1 },
  ])("does not invent a readable source distribution: %j", (source_counts) => {
    render(<EventEvidence event={{ ...receipt, source_counts }} />);
    expect(screen.getByText("单材料线索")).toBeTruthy();
    expect(screen.getByText(/可读成员来源分布：待确定/)).toBeTruthy();
  });

  it("renders an old response with missing evidence fields as unknown", () => {
    render(<EventEvidence event={{ revision: 1 }} />);
    expect(screen.getByText("证据范围待确定")).toBeTruthy();
    expect(screen.getByText(/计数或证据状态缺失/)).toBeTruthy();
    expect(screen.queryByText("单材料线索")).toBeNull();
  });
});

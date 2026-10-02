// @vitest-environment happy-dom
import {
  fireEvent,
  render,
  screen,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EditionDetail } from "@/app/editions/components/edition-detail";

const mocks = vi.hoisted(() => ({
  read: vi.fn(),
  revisions: vi.fn(),
  correct: vi.fn(),
  push: vi.fn(),
}));
vi.mock("@/api/rizhouyuekan", () => ({
  getReportEdition: mocks.read,
  listReportEditionRevisions: mocks.revisions,
  correctReportEdition: mocks.correct,
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));

function edition(
  status: HotKeyAPI.EditionDetailView["status"] = "complete",
): HotKeyAPI.EditionDetailView {
  return {
    id: "edition-1",
    kind: "daily",
    key: "2026-10-01",
    revision: 1,
    status,
    generator: "template",
    window_start: "2026-09-30T16:00:00Z",
    window_end: "2026-10-01T16:00:00Z",
    title: "已许可标题",
    valid: status === "complete",
    failure_code: null,
    created_at: "2026-10-02T02:00:00Z",
    job_id: "job-1",
    body_markdown: "正文",
    ai_call_id: null,
    reason: "验收",
    historical_revision: false,
    content:
      status === "complete"
        ? {
            title: "已许可标题",
            lead: "已许可导读",
            highlights: [],
            sections: [],
            flashes: [],
            themes: [],
            entries: [],
            metrics: {
              selected_count: 1,
              facts_count: 1,
              sources_count: 1,
              first_party_count: 1,
              models_released: 0,
              repeats_suppressed: 0,
              backfill_unknown_count: 0,
              daily_editions_covered: 0,
            },
          }
        : null,
  };
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.revisions.mockResolvedValue([]);
});
afterEach(cleanup);
describe("Edition reading", () => {
  it("removes the whole old body when a refresh reports withdrawn material", async () => {
    mocks.read
      .mockResolvedValueOnce(edition())
      .mockResolvedValueOnce(edition("stale"));
    render(<EditionDetail editionId="edition-1" />);
    await screen.findAllByText("已许可导读");
    fireEvent.click(screen.getByRole("button", { name: "刷新刊期" }));
    await screen.findByText("材料已变更");
    expect(screen.queryAllByText("已许可导读")).toHaveLength(0);
    expect(screen.queryByText("已许可标题")).toBeNull();
    expect(screen.queryByText("当前刊期 Markdown")).toBeNull();
  });

  it("shows unknown delivery with the existing job and does not start another generation", async () => {
    mocks.read.mockResolvedValue(edition("unknown"));
    render(<EditionDetail editionId="edition-1" />);
    await screen.findByText("响应待核实");
    expect(
      screen.getByRole("link", { name: "查看任务记录" }).getAttribute("href"),
    ).toBe("/jobs/job-1");
    expect(mocks.correct).not.toHaveBeenCalled();
  });

  it("does not keep a previously readable body after a failed permission check", async () => {
    mocks.read
      .mockResolvedValueOnce(edition())
      .mockRejectedValueOnce(new Error("offline"));
    render(<EditionDetail editionId="edition-1" />);
    await screen.findAllByText("已许可导读");
    fireEvent.click(screen.getByRole("button", { name: "刷新刊期" }));
    await waitFor(() =>
      expect(screen.queryAllByText("已许可导读")).toHaveLength(0),
    );
    expect(screen.getByText("正文暂不可读")).toBeTruthy();
  });
});

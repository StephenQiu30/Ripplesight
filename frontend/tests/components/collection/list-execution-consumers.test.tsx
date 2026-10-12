// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/api/caijirenwu", () => ({ getCollectionJob: api.get }));
import { JobHistoryCard } from "@/app/jobs/components/job-history";
import { TopicRunResult } from "@/app/monitors/[topicId]/components/topic-run-actions";
import { CoverageWindowDetail } from "@/app/sources/components/coverage-window-detail";
import { ContentDiscoveryList } from "@/app/content/[contentId]/components/content-detail";

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
const receipt = {
  id: "job-a",
  kind: "keyword.search",
  collection_counts: counts,
  collection_executions: [
    {
      execution_epoch: 2,
      collection_cycle_no: 1,
      started_at: "2026-10-12T00:00:00Z",
      finished_at: null,
      outcome: null,
      counts,
    },
  ],
  collection_executions_has_more: false,
};
const row: HotKeyAPI.CollectionCoverageView = {
  window_id: "window-a",
  source_key: "hackernews",
  capability: "search",
  topic_id: null,
  due_at: "2026-10-12T00:00:00Z",
  window_start: "2026-10-11T00:00:00Z",
  window_end: "2026-10-12T00:00:00Z",
  admission_state: "accepted",
  admission_reason: null,
  current_connection_version: 1,
  job_connection_version: 1,
  job_id: "job-a",
  job_status: "running",
  attempts: [],
  started_at: "2026-10-12T00:00:00Z",
  finished_at: null,
  last_success_at: null,
  coverage_status: "partial",
  terminal_evidence: null,
  stop_reason: null,
  request_count: 1,
  request_attempt_count: 2,
  page_count: 1,
  observed_count: null,
  inserted_count: null,
  stored_observation_count: null,
  unique_content_count: null,
  identity_count_basis: null,
  updated_count: null,
  unchanged_count: null,
  unclassified_count: null,
  analysis: null,
  budgets: null,
  gaps: [],
  content_ids: [],
  snapshot_ids: [],
};
const job: HotKeyAPI.JobHistoryItemView = {
  id: "job-a",
  kind: "keyword.search",
  source_key: "hackernews",
  source_capability: "search",
  status: "running",
  requests_sent: 2,
  items_saved: 5,
  created_at: "2026-10-12T00:00:00Z",
  started_at: "2026-10-12T00:00:01Z",
  completed_at: null,
  next_run_at: null,
};
const run: HotKeyAPI.MonitorTopicRunView = {
  operation_id: "op-a",
  topic_id: "topic-a",
  topic_version: 2,
  sources: [
    { source_key: "hackernews", job_ids: ["job-a"], skip_reason: null },
    { source_key: "other", job_ids: [], skip_reason: "rate_limited" },
  ],
};
const discovery: HotKeyAPI.ContentDiscoveryView = {
  job_id: "job-a",
  configuration_ref: "topic-a",
  configuration_version: 2,
  first_observed_at: "2026-10-12T00:00:01Z",
  scan_kind: "new_scan",
};
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it.each(["jobs", "coverage", "accepted", "discoveries"])(
  "%s consumes the explicit task reference lazily and preserves the round denominator",
  async (consumer) => {
    api.get.mockResolvedValue(receipt);
    if (consumer === "jobs") render(<JobHistoryCard job={job} />);
    if (consumer === "coverage")
      render(<CoverageWindowDetail row={row} onClose={() => {}} />);
    if (consumer === "accepted")
      render(<TopicRunResult result={run} sourceNames={{}} />);
    if (consumer === "discoveries")
      render(<ContentDiscoveryList discoveries={[discovery]} />);
    expect(api.get).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", {
        name: consumer === "jobs" ? "查看累计与逐轮计量" : "查看逐轮摘要",
      }),
    );
    const rounds = await screen.findByRole("region", { name: "单轮执行差分" });
    expect(api.get).toHaveBeenCalledOnce();
    expect(api.get.mock.calls[0][0]).toEqual({ job_id: "job-a" });
    expect(within(rounds).getAllByText("分母：4 个唯一身份")).toHaveLength(4);
    expect(within(rounds).getByText(/尚未收尾，计量仍会变化/)).toBeTruthy();
    if (consumer !== "jobs")
      expect(
        screen.getByText(/不是当前覆盖窗口、主题整轮或单份材料的独立增量/),
      ).toBeTruthy();
  },
);
it("offers no execution read for a window without a task", () => {
  render(
    <CoverageWindowDetail row={{ ...row, job_id: null }} onClose={() => {}} />,
  );
  expect(screen.queryByRole("button", { name: "查看逐轮摘要" })).toBeNull();
  expect(api.get).not.toHaveBeenCalled();
});
it("does not invent a task for skipped sources or an empty discovery list", () => {
  render(
    <>
      <TopicRunResult
        result={{
          ...run,
          sources: [
            { source_key: "other", job_ids: [], skip_reason: "rate_limited" },
          ],
        }}
        sourceNames={{}}
      />
      <ContentDiscoveryList discoveries={[]} />
    </>,
  );
  expect(screen.queryByRole("button", { name: "查看逐轮摘要" })).toBeNull();
  expect(api.get).not.toHaveBeenCalled();
});
it("keeps accepted tasks independent rather than aggregating the source's jobs", async () => {
  api.get.mockImplementation(({ job_id }: { job_id: string }) =>
    Promise.resolve({
      ...receipt,
      id: job_id,
      collection_executions:
        job_id === "job-a" ? receipt.collection_executions : [],
    }),
  );
  render(
    <TopicRunResult
      result={{
        ...run,
        sources: [{ ...run.sources[0], job_ids: ["job-a", "job-b"] }],
      }}
      sourceNames={{}}
    />,
  );
  const buttons = screen.getAllByRole("button", { name: "查看逐轮摘要" });
  fireEvent.click(buttons[0]);
  await screen.findByRole("region", { name: "单轮执行差分" });
  expect(api.get).toHaveBeenCalledOnce();
  fireEvent.click(buttons[1]);
  await screen.findByText(/尚无实际领取记录/);
  expect(screen.getAllByText("1 个身份")).toHaveLength(4);
  expect(api.get).toHaveBeenCalledTimes(2);
});

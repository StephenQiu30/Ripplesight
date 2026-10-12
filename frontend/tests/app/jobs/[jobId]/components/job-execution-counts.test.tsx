// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { JobExecutionCounts } from "@/app/jobs/[jobId]/components/job-execution-counts";

const counts: HotKeyAPI.JobCollectionCountsView = {
  identity_count_basis: "frozen_receipt_identity_v2",
  observed_count: 12,
  stored_observation_count: 9,
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
afterEach(cleanup);

it("uses the execution denominator and separates budget cycle and cumulative readings", () => {
  render(<JobExecutionCounts job={{ collection_executions: [execution] }} />);
  const panel = screen.getByRole("region", { name: "单轮执行差分" });
  expect(
    within(panel).getByRole("button", {
      name: "第 2 执行轮 · 预算周期 1 · 失败",
    }),
  ).toBeTruthy();
  expect(within(panel).getByText(/累计量与单轮分别读取/)).toBeTruthy();
  expect(within(panel).getByText("已记录上游返回")).toBeTruthy();
  expect(within(panel).getAllByText("分母：4 个唯一身份")).toHaveLength(4);
  expect(within(panel).getByText(/合计为本执行轮唯一身份数/)).toBeTruthy();
  expect(within(panel).getAllByText("1 个身份")).toHaveLength(4);
  expect(
    within(panel).getByText(/完整历史依据证明首次出现，并归属本执行轮/),
  ).toBeTruthy();
});
it.each([undefined, null])(
  "keeps missing execution history unknown (%s)",
  (collection_executions) => {
    render(<JobExecutionCounts job={{ collection_executions }} />);
    expect(screen.getByText(/执行轮次记录未知/)).toBeTruthy();
    expect(screen.queryByRole("region", { name: "采集计量" })).toBeNull();
  },
);
it("distinguishes an explicit empty history from unknown", () => {
  render(<JobExecutionCounts job={{ collection_executions: [] }} />);
  expect(screen.getByText(/尚无实际领取记录/)).toBeTruthy();
});
it("does not backfill an unattributed historical execution", () => {
  render(
    <JobExecutionCounts
      job={{ collection_executions: [{ ...execution, counts: null }] }}
    />,
  );
  expect(screen.getByText(/本轮缺少可靠归属/)).toBeTruthy();
  expect(screen.queryByText("1 个身份")).toBeNull();
});
it("preserves unknown upstream and known zero identities", () => {
  render(
    <JobExecutionCounts
      job={{
        collection_executions: [
          {
            ...execution,
            counts: {
              ...counts,
              observed_count: null,
              stored_observation_count: 0,
              unique_content_count: 0,
              inserted_count: 0,
              updated_count: 0,
              unchanged_count: 0,
              unclassified_count: 0,
            },
          },
        ],
      }}
    />,
  );
  expect(screen.getByText("未知")).toBeTruthy();
  expect(screen.getAllByText("0 个身份")).toHaveLength(4);
  expect(screen.getAllByText("分母：0 个唯一身份")).toHaveLength(4);
});
it("labels a running execution provisional and keeps retained facts", () => {
  render(
    <JobExecutionCounts
      job={{
        collection_executions: [
          { ...execution, finished_at: null, outcome: null },
        ],
      }}
    />,
  );
  expect(screen.getByText(/尚未收尾，计量仍会变化/)).toBeTruthy();
  expect(screen.getAllByText("1 个身份")).toHaveLength(4);
});
it.each(["expired", "succeeded", "cancelled", "delayed", "failed"] as const)(
  "retains partial receipts for %s",
  (outcome) => {
    render(
      <JobExecutionCounts
        job={{ collection_executions: [{ ...execution, outcome }] }}
      />,
    );
    expect(screen.getByText(/失败、取消或过期仍保留/)).toBeTruthy();
    expect(screen.getAllByText("1 个身份")).toHaveLength(4);
  },
);
it("discloses older rounds independently and labels truncated history", () => {
  render(
    <JobExecutionCounts
      job={{
        collection_executions: [
          execution,
          { ...execution, execution_epoch: 1 },
        ],
        collection_executions_has_more: true,
      }}
    />,
  );
  expect(screen.queryByRole("heading", { name: "第 1 执行轮计量" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /第 1 执行轮/ }));
  expect(screen.getByRole("heading", { name: "第 1 执行轮计量" })).toBeTruthy();
  expect(screen.getByText(/仅展示最近 20 执行轮/)).toBeTruthy();
});

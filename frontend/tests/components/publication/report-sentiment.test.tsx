// @vitest-environment happy-dom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ReportSentiment } from "@/components/publication/report-sentiment";
import { readableHomeReading } from "@/app/components/home-format";
import {
  publicItem,
  publicStory,
  reportSentiment,
} from "../../app/components/home-fixtures";

afterEach(cleanup);
it("shows both denominators, exclusions and public evidence without claiming a surge", () => {
  render(
    <ReportSentiment sentiment={reportSentiment} reports={[publicItem]} />,
  );
  expect(screen.getByText("过去24小时 · 有效 8/12")).toBeTruthy();
  expect(screen.getByText("前一24小时 · 有效 0/5")).toBeTruthy();
  expect(screen.getByText(/负面占有效样本 25%/)).toBeTruthy();
  expect(screen.getByText(/负面占有效样本 未知/)).toBeTruthy();
  expect(screen.getByText(/排除：未分析 2 · 补录 1 · 分析失败 1/)).toBeTruthy();
  expect(screen.getByText(/不代表评论民意/)).toBeTruthy();
  expect(screen.getByText(/样本统计本身不判定突增/)).toBeTruthy();
  expect(
    screen
      .getByRole("link", { name: "公开资讯测试条目 · 负面" })
      .getAttribute("href"),
  ).toBe(publicItem.reading_url);
});
it("keeps missing analysis unknown in compact cards and empty panels", () => {
  const { rerender } = render(<ReportSentiment compact />);
  expect(screen.getByText("报道情感 暂无公开分析依据")).toBeTruthy();
  rerender(<ReportSentiment />);
  expect(screen.getByText("暂无可用的公开报道分析依据。")).toBeTruthy();
});
it.each(["unavailable", "failed", "forbidden"])(
  "clears all derived sentiment for %s",
  (state) => {
    const reading = readableHomeReading({
      stories: [publicStory],
      editions: [],
      sentiment: reportSentiment,
      unavailable: state === "unavailable" ? ["stories"] : [],
      failures:
        state === "unavailable"
          ? {}
          : { stories: { status: state === "forbidden" ? 403 : 503 } },
    });
    expect(reading.sentiment).toBeUndefined();
    expect(reading.stories).toEqual([]);
  },
);

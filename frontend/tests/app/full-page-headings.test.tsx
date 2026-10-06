// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ContentDetail } from "@/app/content/[contentId]/components/content-detail";
import { JobDetail } from "@/app/jobs/[jobId]/components/job-detail";
import { JobHistory } from "@/app/jobs/components/job-history";
import { HotlistWorkspace } from "@/app/hotlists/components/hotlist-workspace";
import { TopicEditor } from "@/app/monitors/[topicId]/components/topic-editor";
import PublicStoryLoading from "@/app/discover/stories/[eventId]/loading";
import { expectOnePageHeading } from "../page-heading";

const api = vi.hoisted(() => ({
  content: vi.fn(),
  job: vi.fn(),
  jobs: vi.fn(),
  hotlists: vi.fn(),
  topic: vi.fn(),
}));
vi.mock("@/api/zuopinziliao", () => ({ getContentRecord: api.content }));
vi.mock("@/api/caijirenwu", () => ({
  getCollectionJob: api.job,
  listCollectionJobs: api.jobs,
}));
vi.mock("@/api/rebang", () => ({ listHotlistSources: api.hotlists }));
vi.mock("@/api/jiankongzhuti", () => ({ getMonitorTopic: api.topic }));
vi.mock("@/api/laiyuannengli", () => ({
  listSourceCapabilities: () =>
    Promise.resolve({ items: [], next_cursor: null }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  for (const request of Object.values(api))
    request.mockReturnValue(new Promise(() => {}));
});
afterEach(cleanup);

it.each([
  ["作品", <ContentDetail key="content" contentId="content" />, "正在读取作品"],
  ["任务详情", <JobDetail key="job" jobId="job" />, "正在读取任务"],
  ["任务记录", <JobHistory key="jobs" />, "正在读取任务"],
  ["热榜", <HotlistWorkspace key="hotlists" />, "正在加载来源"],
  ["监控主题", <TopicEditor key="topic" topicId="topic" />, "正在读取主题"],
  ["公开事件", <PublicStoryLoading key="story" />, "正在读取公开事件"],
] as const)(
  "keeps one h1 during full-page %s loading",
  (_, component, title) => {
    render(component);
    expect(screen.getByRole("status", { name: title })).toBeTruthy();
    expectOnePageHeading();
    expect(screen.getByRole("heading", { level: 1 }).className).toContain(
      "sr-only",
    );
  },
);

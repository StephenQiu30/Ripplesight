// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Heading } from "@/components/ui/content";
import { AlertHistory } from "@/components/monitors/alert-history";
import { TopicAlerts } from "@/components/monitors/topic-alerts";
import { EditorialTopicSources } from "@/components/monitors/editorial-topic-sources";
import { ApiRequestError } from "@/request";
import { expectOnePageHeading } from "../../page-heading";

const api = vi.hoisted(() => ({
  history: vi.fn(),
  alerts: vi.fn(),
  sources: vi.fn(),
}));
vi.mock("@/api/gerentufagaojing", () => ({
  listAlertHistory: api.history,
  listAlerts: api.alerts,
}));
vi.mock("@/api/jiankongzhuti", () => ({
  listMonitorEditorialSources: api.sources,
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

const blocks = [
  {
    name: "history",
    title: "正在读取评估历史",
    component: <AlertHistory ruleId="rule" />,
    request: api.history,
    empty: "尚无评估记录",
    failure: "暂时无法读取告警历史",
    forbidden: "无权读取告警历史",
  },
  {
    name: "rules",
    title: "正在读取告警规则",
    component: <TopicAlerts topicId="topic" />,
    request: api.alerts,
    empty: "这个主题尚无告警规则",
    failure: "暂时无法读取告警规则",
    forbidden: "无权读取主题告警",
  },
  {
    name: "sources",
    title: "正在读取订阅流",
    component: (
      <EditorialTopicSources
        selectedProfileIds={[]}
        onChange={vi.fn()}
        disabled={false}
      />
    ),
    request: api.sources,
    empty: "还没有获准的订阅流。可以先保存关注，来源准备好后再选择。",
    failure: "订阅流暂时不可用",
    forbidden: "订阅流暂时不可用",
  },
] as const;

it.each(blocks)(
  "preserves the page h1 while $name loads",
  ({ component, request, title }) => {
    request.mockReturnValue(new Promise(() => {}));
    render(
      <>
        <Heading level={1}>监控主题</Heading>
        {component}
      </>,
    );
    expect(screen.getByLabelText(title)).toBeTruthy();
    expectOnePageHeading();
  },
);

it.each(blocks)(
  "preserves the page h1 for an empty $name block",
  async ({ component, request, empty }) => {
    request.mockResolvedValue([]);
    render(
      <>
        <Heading level={1}>监控主题</Heading>
        {component}
      </>,
    );
    await screen.findByText(empty);
    expectOnePageHeading();
  },
);

it.each(
  blocks.flatMap((block) =>
    [401, 403, 503].map((status) => ({ ...block, status })),
  ),
)(
  "keeps $name HTTP $status errors at level 2",
  async ({ component, request, status, failure, forbidden }) => {
    request.mockRejectedValue(
      new ApiRequestError({
        kind: "http",
        status,
        code: "access_failed",
        message: "failed",
      }),
    );
    render(
      <>
        <Heading level={1}>监控主题</Heading>
        {component}
      </>,
    );
    await screen.findByRole("heading", {
      level: 2,
      name: status === 503 ? failure : forbidden,
    });
    expectOnePageHeading();
  },
);

it("keeps stale and empty history states below the same page heading", async () => {
  api.history
    .mockResolvedValueOnce([])
    .mockRejectedValueOnce(new Error("offline"));
  render(
    <>
      <Heading level={1}>突发告警</Heading>
      <AlertHistory ruleId="rule" />
    </>,
  );
  await screen.findByRole("heading", { level: 2, name: "尚无评估记录" });
  expectOnePageHeading();
  fireEvent.click(screen.getByRole("button", { name: "刷新历史" }));
  await screen.findByText("已过期");
  expect(
    screen.getByRole("heading", { level: 2, name: /暂时无法读取告警历史/ }),
  ).toBeTruthy();
  expectOnePageHeading();
});

// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { EditorialSourcePreview } from "@/app/editorial-sources/components/editorial-source-preview";

const notifications = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: notifications }));

const api = vi.hoisted(() => ({
  sample: vi.fn(),
  remote: vi.fn(),
  read: vi.fn(),
  review: vi.fn(),
}));
vi.mock("@/api/bianjilaiyuan", () => ({
  previewEditorialSourceSample: api.sample,
  previewStoredEditorialSource: api.remote,
  getEditorialSourcePreview: api.read,
  reviewEditorialSourcePreview: api.review,
}));
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);
const configuration = {
  kind: "rss",
  feed_url: "https://example.com/feed",
  allowed_hosts: ["example.com"],
};
const props = {
  token: "controlled",
  configurationJson: JSON.stringify(configuration),
  kind: "rss" as const,
  profileId: "profile-one",
  expectedRevision: 7,
  sourceEnabled: true,
};
const sample = {
  mode: "sample",
  status: "complete",
  kind: "rss",
  count: 1,
  ms: 4,
  requests: 0,
  reason: null,
  items: [
    {
      title: "受控文章",
      url: "https://example.com/item",
      published_at: null,
      excerpt: "公开短摘要",
    },
  ],
};
function reason() {
  fireEvent.change(screen.getByLabelText("试抓原因"), {
    target: { value: "验证配置规则" },
  });
}
it("parses the current draft and a bounded local sample without a remote request or ingestion", async () => {
  api.sample.mockResolvedValue(sample);
  render(<EditorialSourcePreview {...props} />);
  reason();
  fireEvent.change(screen.getByLabelText("本地样本文本"), {
    target: { value: "<rss/>" },
  });
  fireEvent.click(screen.getByRole("button", { name: "解析本地样本" }));
  await screen.findByText("受控文章");
  expect(api.sample.mock.calls[0]).toEqual([
    {
      operation_id: expect.any(String),
      reason: "验证配置规则",
      configuration,
      sample: "<rss/>",
    },
    {
      headers: {
        "X-HotKey-Operator-Token": "controlled",
        "X-HotKey-CSRF": "1",
      },
    },
  ]);
  expect(api.remote).not.toHaveBeenCalled();
  expect(api.read).not.toHaveBeenCalled();
  expect(screen.getByText(/请求数 0/)).toBeTruthy();
});
it("queues a remote preview with the captured profile revision and only reads its result explicitly", async () => {
  api.remote.mockResolvedValue({ id: "preview-job", status: "queued" });
  api.read.mockResolvedValue({
    job: { id: "preview-job", status: "succeeded" },
    preview: { ...sample, mode: "remote", requests: 1 },
  });
  render(<EditorialSourcePreview {...props} />);
  reason();
  fireEvent.click(screen.getByRole("button", { name: "受理远程试抓" }));
  await screen.findByRole("button", { name: "读取试抓结果" });
  expect(api.remote.mock.calls[0][0]).toEqual({ profile_id: "profile-one" });
  expect(api.remote.mock.calls[0][1]).toMatchObject({
    expected_revision: 7,
    reason: "验证配置规则",
    operation_id: expect.any(String),
  });
  expect(api.read).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "读取试抓结果" }));
  await screen.findByText("受控文章");
  expect(api.read.mock.calls[0][0]).toEqual({ job_id: "preview-job" });
  expect(api.remote).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/不写入正式材料/)).toBeTruthy();
});
it("keeps an unknown remote result distinct and never automatically queues a paid retry", async () => {
  api.remote.mockResolvedValue({ id: "preview-job", status: "queued" });
  api.read.mockResolvedValue({
    job: { id: "preview-job", status: "failed" },
    preview: {
      ...sample,
      mode: "remote",
      status: "unknown",
      count: 0,
      items: [],
      reason: "source_request_unknown",
      requests: 1,
    },
  });
  render(<EditorialSourcePreview {...props} />);
  reason();
  fireEvent.click(screen.getByRole("button", { name: "受理远程试抓" }));
  fireEvent.click(await screen.findByRole("button", { name: "读取试抓结果" }));
  await screen.findByText(/结果未知/);
  expect(api.remote).toHaveBeenCalledTimes(1);
  expect(
    (screen.getByRole("button", { name: "受理远程试抓" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
});
it("reviews the exact unknown operation with profile CAS and permits only an explicit fresh remote attempt", async () => {
  api.remote.mockImplementation((_params, input) =>
    Promise.resolve({
      id: "preview-job",
      operation_id: input.operation_id,
      status: "queued",
    }),
  );
  api.read.mockResolvedValue({
    job: { id: "preview-job", status: "failed" },
    preview: { ...sample, mode: "remote", status: "unknown", items: [] },
  });
  api.review.mockResolvedValue({
    job_id: "preview-job",
    profile_id: "profile-one",
    reviewed: true,
    status: "unknown",
    revision: 7,
  });
  render(<EditorialSourcePreview {...props} />);
  reason();
  fireEvent.click(screen.getByRole("button", { name: "受理远程试抓" }));
  fireEvent.click(await screen.findByRole("button", { name: "读取试抓结果" }));
  const review = await screen.findByRole("button", { name: "已核对未知试抓" });
  fireEvent.click(review);
  await screen.findByText(/已记录人工核对；原结果仍为未知/);
  const originalOperation = api.remote.mock.calls[0][1].operation_id;
  expect(api.review.mock.calls[0]).toEqual([
    { job_id: "preview-job" },
    {
      operation_id: expect.any(String),
      preview_operation_id: originalOperation,
      expected_revision: 7,
      reason: "验证配置规则",
    },
    {
      headers: {
        "X-HotKey-Operator-Token": "controlled",
        "X-HotKey-CSRF": "1",
      },
    },
  ]);
  expect(api.remote).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/结果未知/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "受理远程试抓" }));
  await waitFor(() => expect(api.remote).toHaveBeenCalledTimes(2));
  expect(api.remote.mock.calls[1][1].operation_id).not.toBe(originalOperation);
});
it("does not unlock an unknown request when manual review fails and preserves the review operation for retry", async () => {
  api.remote.mockResolvedValue({
    id: "preview-job",
    operation_id: "original-operation",
    status: "queued",
  });
  api.read.mockResolvedValue({
    job: { id: "preview-job", status: "failed" },
    preview: { ...sample, mode: "remote", status: "unknown", items: [] },
  });
  api.review.mockRejectedValue(new Error("controlled unknown response"));
  render(<EditorialSourcePreview {...props} />);
  reason();
  fireEvent.click(screen.getByRole("button", { name: "受理远程试抓" }));
  fireEvent.click(await screen.findByRole("button", { name: "读取试抓结果" }));
  const review = await screen.findByRole("button", { name: "已核对未知试抓" });
  fireEvent.click(review);
  await waitFor(() => expect(notifications.error).toHaveBeenCalled());
  expect(screen.queryByRole("alert")).toBeNull();
  expect(
    (screen.getByRole("button", { name: "受理远程试抓" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  fireEvent.click(review);
  await waitFor(() => expect(api.review).toHaveBeenCalledTimes(2));
  expect(api.review.mock.calls[0][1].operation_id).toBe(
    api.review.mock.calls[1][1].operation_id,
  );
  expect(api.remote).toHaveBeenCalledTimes(1);
});
it("clears the preview context on unmount and rejects unsupported source types", async () => {
  let complete!: (value: object) => void;
  api.sample.mockImplementation(
    () =>
      new Promise((resolve) => {
        complete = resolve;
      }),
  );
  const view = render(<EditorialSourcePreview key="rss" {...props} />);
  reason();
  fireEvent.change(screen.getByLabelText("本地样本文本"), {
    target: { value: "<rss/>" },
  });
  fireEvent.click(screen.getByRole("button", { name: "解析本地样本" }));
  await waitFor(() => expect(api.sample).toHaveBeenCalledTimes(1));
  view.rerender(
    <EditorialSourcePreview
      key="external"
      {...props}
      kind="external"
      configurationJson='{"kind":"external"}'
    />,
  );
  complete(sample);
  await screen.findByText(/公众号与外部摄入不支持/);
  expect(screen.queryByText("受控文章")).toBeNull();
  expect(api.remote).not.toHaveBeenCalled();
});
it("makes no anonymous preview and rejects a sample exceeding the byte limit", async () => {
  const view = render(<EditorialSourcePreview {...props} token="" />);
  reason();
  expect(
    (screen.getByRole("button", { name: "解析本地样本" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  view.rerender(<EditorialSourcePreview {...props} />);
  fireEvent.change(screen.getByLabelText("本地样本文本"), {
    target: { value: "中".repeat(333_334) },
  });
  fireEvent.click(screen.getByRole("button", { name: "解析本地样本" }));
  await waitFor(() =>
    expect(notifications.error).toHaveBeenCalledWith(
      expect.stringContaining("样本不能超过 1 MB"),
    ),
  );
  expect(api.sample).not.toHaveBeenCalled();
});
it("accepts exactly one million UTF-8 bytes rather than counting characters", async () => {
  api.sample.mockResolvedValue(sample);
  render(<EditorialSourcePreview {...props} />);
  reason();
  const bounded = `${"中".repeat(333_333)}a`;
  fireEvent.change(screen.getByLabelText("本地样本文本"), {
    target: { value: bounded },
  });
  fireEvent.click(screen.getByRole("button", { name: "解析本地样本" }));
  await screen.findByText("受控文章");
  expect(api.sample.mock.calls[0][0].sample).toBe(bounded);
  expect(api.remote).not.toHaveBeenCalled();
});

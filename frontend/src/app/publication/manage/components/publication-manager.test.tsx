// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { requestPublicationMediaMirror } from "@/api/fabumeiti";
import { PublicationManager } from "./publication-manager";

const policies = vi.hoisted(() => ({ list: vi.fn(), save: vi.fn() }));
vi.mock("@/api/gongkaifabu", () => ({
  listPublicationPolicies: policies.list,
  savePublicationSourcePolicy: policies.save,
  getPublicationRepublishRun: vi.fn(),
  overridePublication: vi.fn(),
  republishPublicationSource: vi.fn(),
}));

vi.mock("@/api/fabumeiti", () => ({
  requestPublicationMediaMirror: vi.fn(),
  getPublicationMediaMirrorRun: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
});

it("preserves the explicit media operation identity on replay and clears the in-memory token", async () => {
  const receipt: HotKeyAPI.MediaMirrorRunView = {
    id: "00000000-0000-4000-8000-000000000002",
    job_id: "00000000-0000-4000-8000-000000000003",
    content_id: "00000000-0000-4000-8000-000000000004",
    content_version_id: "00000000-0000-4000-8000-000000000005",
    policy_revision: 1,
    status: "unknown",
    candidate_count: 1,
    available_count: 0,
    unavailable_count: 1,
    reason: "interrupted_request_or_object_write",
    replayed: true,
  };
  vi.mocked(requestPublicationMediaMirror).mockResolvedValue(receipt);
  render(<PublicationManager />);
  fireEvent.change(screen.getByLabelText("操作员令牌"), {
    target: { value: "controlled-token" },
  });
  const button = screen.getByRole("button", { name: "受理媒体任务" });
  const form = button.closest("form")!;
  const scoped = within(form);
  fireEvent.change(scoped.getByLabelText("条目编号"), {
    target: { value: receipt.content_id },
  });
  fireEvent.change(scoped.getByLabelText("固定正文版本编号"), {
    target: { value: receipt.content_version_id },
  });
  fireEvent.change(scoped.getByLabelText("当前许可策略修订"), {
    target: { value: "1" },
  });
  fireEvent.submit(form);
  await waitFor(() =>
    expect(screen.getByText(/已复用同版本任务/)).toBeTruthy(),
  );
  const first = vi.mocked(requestPublicationMediaMirror).mock.calls[0];
  expect(first[1].content_version_id).toBe(receipt.content_version_id);
  expect(first[2]?.headers).toEqual({
    "X-HotKey-Operator-Token": "controlled-token",
    "X-HotKey-CSRF": "1",
  });
  fireEvent.submit(form);
  await waitFor(() =>
    expect(requestPublicationMediaMirror).toHaveBeenCalledTimes(2),
  );
  expect(
    vi.mocked(requestPublicationMediaMirror).mock.calls[1][1].operation_id,
  ).toBe(first[1].operation_id);
  expect(localStorage.length).toBe(0);
  fireEvent.click(screen.getByRole("button", { name: "清除令牌" }));
  expect((screen.getByLabelText("操作员令牌") as HTMLInputElement).value).toBe(
    "",
  );
  expect(screen.queryByText(/已复用同版本任务/)).toBeNull();
  expect((button as HTMLButtonElement).disabled).toBe(true);
});

it("edits only source permissions and leaves fixed material format outside the policy form", async () => {
  const policy = {
    source_key: "controlled-source",
    revision: 3,
    participation_mode: "editorial",
    body_format: "html",
    site_fulltext: true,
    syndicate_fulltext: false,
    indexable: false,
    license_name: "受控许可",
    release_delay_seconds: 0,
  };
  policies.list.mockResolvedValue([policy]);
  policies.save.mockResolvedValue({ ...policy, revision: 4 });
  render(<PublicationManager />);
  fireEvent.change(screen.getByLabelText("操作员令牌"), {
    target: { value: "controlled-token" },
  });
  fireEvent.click(screen.getByRole("button", { name: "读取策略" }));
  await screen.findByText(/已读取当前策略/);
  expect(screen.queryByLabelText("原文格式")).toBeNull();
  expect(screen.getByText(/正文格式由固定材料记录决定/)).toBeTruthy();
  const form = screen.getByLabelText("来源标识").closest("form")!;
  fireEvent.change(within(form).getByLabelText("来源标识"), {
    target: { value: policy.source_key },
  });
  fireEvent.change(within(form).getByLabelText("预期修订（新来源为 0）"), {
    target: { value: "3" },
  });
  fireEvent.change(within(form).getByLabelText("许可名称"), {
    target: { value: policy.license_name },
  });
  fireEvent.change(within(form).getByLabelText("修订原因"), {
    target: { value: "修订当前许可，不改变固定正文格式" },
  });
  fireEvent.submit(form);
  await waitFor(() => expect(policies.save).toHaveBeenCalledOnce());
  const body = policies.save.mock.calls[0][1];
  expect(body.expected_revision).toBe(3);
  expect(body).not.toHaveProperty("body_format");
  expect(body).not.toHaveProperty("format");
});

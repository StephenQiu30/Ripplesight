// @vitest-environment happy-dom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const transport = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/request", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/request")>()),
  default: transport.request,
}));
vi.mock("@/components/monitors/topic-list", () => ({
  TopicList: () => <div>业务主题列表</div>,
}));

import { EventsWorkspace } from "./events-workspace";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Demo workbench", () => {
  it("renders the business workspace without an identity request or logout", () => {
    transport.request.mockRejectedValue(new Error("identity API removed"));
    render(<EventsWorkspace />);

    expect(screen.getByText("业务主题列表")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "新建监控主题" }).getAttribute("href"),
    ).toBe("/monitors/new");
    expect(screen.queryByRole("button", { name: "退出" })).toBeNull();
    expect(screen.queryByText(/验证会话/)).toBeNull();
    expect(transport.request).not.toHaveBeenCalled();
  });
});

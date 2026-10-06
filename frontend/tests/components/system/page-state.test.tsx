// @vitest-environment happy-dom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const router = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";

afterEach(cleanup);

const copy = { eyebrow: "资讯", title: "页面状态", description: "状态说明" };

describe("PageState", () => {
  it("announces loading with hidden skeletons and preserves the provided description", () => {
    const { container } = render(<PageState {...copy} state="loading" />);
    const status = screen.getByRole("status", { name: copy.title });
    expect(status.getAttribute("aria-busy")).toBe("true");
    expect(status.textContent).toContain(copy.description);
    const skeletons = container.querySelectorAll('[data-slot="skeleton"]');
    expect(skeletons.length).toBeGreaterThan(0);
    skeletons.forEach((skeleton) => {
      expect(skeleton.closest('[aria-hidden="true"]')).toBeTruthy();
      expect(skeleton.classList.contains("motion-reduce:animate-none")).toBe(
        true,
      );
    });
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("gives the empty state a real next step", () => {
    render(<PageState {...copy} state="empty" />);
    expect(
      screen.getByRole("heading", { level: 1, name: copy.title }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "探索资讯" }).getAttribute("href"),
    ).toBe("/discover?mode=all");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("keeps a caller's next step and retry handler", () => {
    const retry = vi.fn();
    const view = render(
      <PageState
        {...copy}
        state="empty"
        action={<Button onClick={retry}>新建主题</Button>}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "新建主题" }));
    expect(retry).toHaveBeenCalledTimes(1);
    view.rerender(
      <PageState
        {...copy}
        state="error"
        errorCode="service_unavailable"
        httpStatus={503}
        action={<Button onClick={retry}>重新加载</Button>}
      />,
    );
    const alert = screen.getByRole("alert", { name: copy.title });
    expect(alert.getAttribute("data-slot")).toBe("alert");
    const code = within(alert).getByText("service_unavailable · 503");
    expect(code.tagName).toBe("CODE");
    expect(code.classList.contains("font-mono")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
    expect(retry).toHaveBeenCalledTimes(2);
  });

  it("does not invent an error code or HTTP status when callers provide neither", () => {
    const { container } = render(<PageState {...copy} state="error" />);
    expect(screen.getByRole("alert", { name: copy.title })).toBeTruthy();
    expect(container.querySelector("code")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(router.refresh).toHaveBeenCalledTimes(1);
  });

  it("offers login and public reading for a permission state", () => {
    render(<PageState {...copy} state="forbidden" />);
    expect(
      screen.getByRole("link", { name: "登录" }).getAttribute("href"),
    ).toBe("/login");
    expect(
      screen.getByRole("link", { name: "返回首页" }).getAttribute("href"),
    ).toBe("/");
  });

  it("preserves a caller's login return URL and adds public reading", () => {
    render(
      <PageState
        {...copy}
        state="forbidden"
        action={
          <Button asChild>
            <a href="/login?returnTo=%2Faccount">登录账户</a>
          </Button>
        }
      />,
    );
    expect(
      screen.getByRole("link", { name: "登录账户" }).getAttribute("href"),
    ).toBe("/login?returnTo=%2Faccount");
    expect(screen.getByRole("link", { name: "返回首页" })).toBeTruthy();
  });

  it("marks stale data with the caller's timestamp and keeps adjacent content readable", () => {
    const retry = vi.fn();
    render(
      <>
        <PageState
          {...copy}
          state="stale"
          staleAt="2026-10-06 13:05"
          action={<Button onClick={retry}>重新加载</Button>}
        />
        <p>已保存的正文</p>
      </>,
    );
    const status = screen.getByRole("status", { name: copy.title });
    expect(within(status).getByText("已过期")).toBeTruthy();
    expect(within(status).getByText("2026-10-06 13:05")).toBeTruthy();
    expect(screen.getByText("已保存的正文")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("uses a level-2 heading when nested under an existing page title", () => {
    const view = render(<PageState {...copy} state="error" headingLevel={2} />);
    expect(
      screen.getByRole("heading", { level: 2, name: copy.title }),
    ).toBeTruthy();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    view.rerender(<PageState {...copy} state="empty" headingLevel={2} />);
    expect(
      screen.getByRole("heading", { level: 2, name: copy.title }),
    ).toBeTruthy();
  });
});

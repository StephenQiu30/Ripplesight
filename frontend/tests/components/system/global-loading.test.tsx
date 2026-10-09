// @vitest-environment happy-dom
import { StrictMode, useTransition } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import {
  GlobalLoadingProvider,
  LoadingSignal,
} from "@/components/system/global-loading";
import { HomeLoading } from "@/app/components/home-loading";
import { PageState } from "@/components/system/page-state";

afterEach(cleanup);

it("keeps a single global indicator until every concurrent loading boundary finishes", () => {
  const view = render(
    <StrictMode>
      <GlobalLoadingProvider>
        <HomeLoading />
        <PageState state="loading" title="正在加载详情" description="请稍候" />
      </GlobalLoadingProvider>
    </StrictMode>,
  );
  expect(screen.getAllByRole("status", { name: "全局加载状态" })).toHaveLength(
    1,
  );
  expect(
    document.querySelectorAll('[data-slot="global-loading-indicator"]'),
  ).toHaveLength(1);
  expect(screen.getByRole("status", { name: "全局加载状态" }).textContent).toBe(
    "正在加载，请稍候。",
  );
  view.rerender(
    <StrictMode>
      <GlobalLoadingProvider>
        <HomeLoading />
      </GlobalLoadingProvider>
    </StrictMode>,
  );
  expect(screen.getByRole("status", { name: "全局加载状态" })).toBeTruthy();
  expect(
    document.querySelector('[data-slot="global-loading-indicator"]'),
  ).not.toBeNull();
  view.rerender(
    <StrictMode>
      <GlobalLoadingProvider>
        <PageState state="empty" title="暂无内容" description="稍后再来" />
      </GlobalLoadingProvider>
    </StrictMode>,
  );
  expect(screen.getByRole("status", { name: "全局加载状态" }).textContent).toBe(
    "",
  );
  expect(
    document.querySelector('[data-slot="global-loading-indicator"]'),
  ).toBeNull();
  expect(screen.getByRole("status", { name: "暂无内容" })).toBeTruthy();
});

it("reports a pending transition while retaining content and clears on completion", async () => {
  let finish!: () => void;
  const request = new Promise<void>((resolve) => {
    finish = resolve;
  });
  function Reader() {
    const [pending, startTransition] = useTransition();
    return (
      <>
        <LoadingSignal active={pending} />
        <p>已加载的正文</p>
        <button
          disabled={pending}
          onClick={() => startTransition(() => request)}
        >
          重试
        </button>
      </>
    );
  }
  render(
    <GlobalLoadingProvider>
      <Reader />
    </GlobalLoadingProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(screen.getByRole("status", { name: "全局加载状态" })).toBeTruthy();
  expect(
    document.querySelector('[data-slot="global-loading-indicator"]'),
  ).not.toBeNull();
  expect(screen.getByText("已加载的正文")).toBeTruthy();
  expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
  await act(async () => {
    finish();
    await request;
  });
  expect(screen.getByRole("status", { name: "全局加载状态" }).textContent).toBe(
    "",
  );
  expect(
    document.querySelector('[data-slot="global-loading-indicator"]'),
  ).toBeNull();
});

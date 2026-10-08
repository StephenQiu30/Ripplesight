// @vitest-environment happy-dom

import { act } from "@testing-library/react";
import type { ReactNode } from "react";
import { hydrateRoot, type Root } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => undefined }),
}));
vi.mock("@/components/auth/layout-session", () => ({
  readLayoutSession: async () => null,
}));
vi.mock("@/layout/layout-fonts", () => ({
  layoutFontClassName: "test-font",
}));
vi.mock("@/layout/basic-layout", () => ({
  BasicLayout: ({ children }: { children: ReactNode }) => children,
}));

import RootLayout from "@/app/layout";

let root: Root | undefined;
afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  root = undefined;
  vi.restoreAllMocks();
});

async function serverDocument() {
  const tree = await RootLayout({ children: <main>登录</main> });
  const target = document.implementation.createHTMLDocument();
  target.open();
  target.write("<!DOCTYPE html>" + renderToString(tree));
  target.close();
  return { tree, target };
}

it("hydrates a document with an extension-owned root attribute without warning", async () => {
  const { tree, target } = await serverDocument();
  expect(
    target.documentElement.hasAttribute("data-immersive-translate-page-theme"),
  ).toBe(false);
  target.documentElement.setAttribute(
    "data-immersive-translate-page-theme",
    "light",
  );
  const errors = vi.spyOn(console, "error").mockImplementation(() => {});
  const recoverable = vi.fn();

  await act(async () => {
    root = hydrateRoot(target, tree, { onRecoverableError: recoverable });
  });

  expect(errors).not.toHaveBeenCalled();
  expect(recoverable).not.toHaveBeenCalled();
  expect(target.querySelector("main")?.textContent).toBe("登录");
  expect(
    target.documentElement.getAttribute("data-immersive-translate-page-theme"),
  ).toBe("light");
});

it("still reports a real descendant hydration mismatch", async () => {
  const { tree, target } = await serverDocument();
  target.querySelector("main")!.textContent = "different server content";
  const recoverable = vi.fn();
  vi.spyOn(console, "error").mockImplementation(() => {});

  await act(async () => {
    root = hydrateRoot(target, tree, { onRecoverableError: recoverable });
  });

  expect(recoverable).toHaveBeenCalled();
  expect(target.querySelector("main")?.textContent).toBe("登录");
});

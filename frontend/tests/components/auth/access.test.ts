import { describe, expect, it } from "vitest";

import { isPublicPagePath, safeReturnTo } from "@/components/auth/access";

describe("welcome and workspace access", () => {
  it.each([
    "/",
    "/login",
    "/about",
    "/privacy",
    "/terms",
    "/contact",
    "/changelog",
  ])("keeps %s public", (path) => {
    expect(isPublicPagePath(path)).toBe(true);
  });

  it.each([
    "/topics",
    "/monitors/new",
    "/discover",
    "/reports/daily",
    "/operations/models",
    "/account",
  ])("keeps %s behind login", (path) => {
    expect(isPublicPagePath(path)).toBe(false);
    expect(safeReturnTo(path)).toBe(path);
  });

  it.each([
    undefined,
    "/",
    "/login",
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "/topics/%5cevil",
    "/topics/%0afoo",
    "/api/identity/session",
    "/topics/../api/identity/session",
    "/unknown",
    "/topics-bad",
  ])("rejects an unsafe return target %s", (path) => {
    expect(safeReturnTo(path)).toBe("/topics");
  });

  it("preserves a valid workspace query and anchor", () => {
    expect(safeReturnTo("/jobs/job-1?state=failed#history")).toBe(
      "/jobs/job-1?state=failed#history",
    );
  });
});

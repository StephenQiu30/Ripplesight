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
    "/discover",
    "/discover/topics/ai",
    "/items/content-1",
    "/leaderboard/models/model-1",
    "/reports/daily",
    "/reports/daily/archive",
    "/reports/weekly/archive",
    "/reports/monthly/archive",
    "/reports/daily/2026-10-03",
    "/reports/weekly/2026-W40",
    "/reports/monthly/2026-10",
  ])("keeps %s public", (path) => {
    expect(isPublicPagePath(path)).toBe(true);
  });

  it.each([
    "/topics",
    "/monitors/new",
    "/workspace",
    "/reports/report-1",
    "/reports/weekly/archive/private",
    "/reports/report-1/archive",
    "/reports/weekly/not-a-key",
    "/editions",
    "/codex-resets/manage",
    "/publication/manage",
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

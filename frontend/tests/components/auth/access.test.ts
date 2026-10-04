import { describe, expect, it } from "vitest";

import { isPublicPagePath, safeReturnTo } from "@/components/auth/access";
import { isPublicDistributionPath } from "@/components/auth/public-distribution-path";

describe("welcome and workspace access", () => {
  it.each([
    "/",
    "/login",
    "/about",
    "/privacy",
    "/terms",
    "/contact",
    "/changelog",
    "/feeds",
    "/agent",
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

  it.each([
    "/public/feed.xml",
    "/public/feed/all.xml",
    "/public/feed/daily.xml",
    "/public/feed/category/ai-models.xml",
    "/public/feed/full/category/ai-models.xml",
    "/public/items/00000000-0000-4000-8000-000000000001.md",
    "/public/selected.md",
    "/public/reports/monthly/2026-10.md",
    "/public/agent.md",
    "/public/api/items",
    "/public/api/items/00000000-0000-4000-8000-000000000001",
    "/public/api/hot",
    "/public/api/stories/00000000-0000-4000-8000-000000000001",
    "/public/api/reports/weekly/2026-W40",
    "/public/mcp",
  ])("shares one exact anonymous protocol allowlist for %s", (path) => {
    expect(isPublicDistributionPath(path)).toBe(true);
    expect(isPublicPagePath(path)).toBe(true);
  });

  it.each([
    null,
    "/public",
    "/public/",
    "/public/api/operations",
    "/public/api/content-exports",
    "/public/items/private.jsonld",
    "/public/mcp/extra",
    "/public/feed/../api/operations",
    "/public/api/items%2F..%2Foperations",
    "/public/api/items?owner=other",
    "/feed.xml",
    "/agent.md",
  ])("keeps an unlisted protocol outside the anonymous scope: %s", (path) => {
    expect(isPublicDistributionPath(path)).toBe(false);
    expect(isPublicPagePath(path)).toBe(false);
  });
});

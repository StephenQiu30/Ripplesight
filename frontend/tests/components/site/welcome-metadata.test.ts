import { afterEach, expect, it, vi } from "vitest";

import robots from "@/app/robots";
import sitemap from "@/app/sitemap";
import { welcomeMetadata } from "@/components/site/welcome-metadata";
import nextConfig from "../../../next.config";

afterEach(() => vi.unstubAllEnvs());

it("generates canonical and sharing metadata for the configured welcome site", () => {
  vi.stubEnv("NEXT_PUBLIC_SITE_ORIGIN", "https://welcome.example");
  const data = welcomeMetadata("/", "Ripplesight", "从关键词开始持续关注。");
  expect(data.robots).toEqual({ index: true, follow: true });
  expect(data.alternates?.canonical).toBe("https://welcome.example/");
  expect(data.openGraph).toMatchObject({
    url: "https://welcome.example/",
    siteName: "Ripplesight",
    type: "website",
  });
});

it("includes the public information and explanation pages in the native sitemap", () => {
  vi.stubEnv("NEXT_PUBLIC_SITE_ORIGIN", "https://welcome.example");
  expect(sitemap().map((entry) => new URL(entry.url).pathname)).toEqual([
    "/",
    "/about",
    "/privacy",
    "/terms",
    "/contact",
    "/changelog",
    "/feeds",
    "/agent",
    "/discover",
    "/leaderboard",
    "/reports/daily",
    "/reports/weekly",
    "/reports/monthly",
  ]);
  expect(robots().rules).toMatchObject({
    userAgent: "*",
    allow: expect.arrayContaining([
      "/",
      "/discover",
      "/leaderboard",
      "/reports/weekly",
    ]),
    disallow: expect.arrayContaining([
      "/login",
      "/api/",
      "/topics",
      "/discover",
      "/leaderboard",
      "/account",
    ]),
  });
});

it("keeps robots and sitemap served by Next instead of rewriting to business exports", async () => {
  const configured = await nextConfig.rewrites?.();
  if (!configured || Array.isArray(configured))
    throw new Error("Expected structured export rewrites");
  expect(
    (configured.beforeFiles ?? []).some(
      (entry) =>
        entry.source === "/robots.txt" ||
        entry.source === "/sitemap.xml" ||
        entry.source.startsWith("/sitemaps/"),
    ),
  ).toBe(false);
});

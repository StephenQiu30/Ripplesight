import { expect, it } from "vitest";
import { publicPageMetadata } from "@/components/publication/site-metadata";
const site: HotKeyAPI.PublicSiteMetaView = {
  name: "HotKey",
  version: "1",
  environment: "test",
  description: "受控站点",
  public_base_url: "https://hotkey.example",
  robots_index: false,
  features: {
    editorial_analysis: false,
    model_leaderboard: false,
    codex_monitor: false,
    notifications: false,
    smtp: false,
    media_mirror: false,
    feedback: false,
    external_indexing: false,
  },
};
it("keeps Demo and unpublished or filtered pages noindex while constructing the public canonical and OG path", () => {
  const options = {
    title: "公开模型榜",
    path: "/leaderboard",
    imagePath: "/og/pages/leaderboard.png",
  };
  expect(publicPageMetadata(site, options).robots).toEqual({
    index: false,
    follow: false,
  });
  const enabled = { ...site, robots_index: true };
  expect(
    publicPageMetadata(enabled, { ...options, indexable: false }).robots,
  ).toEqual({ index: false, follow: false });
  const valid = publicPageMetadata(enabled, options);
  expect(valid.robots).toEqual({ index: true, follow: true });
  expect(valid.alternates?.canonical).toBe(
    "https://hotkey.example/leaderboard",
  );
  expect(valid.openGraph?.images).toEqual([
    {
      url: "https://hotkey.example/og/pages/leaderboard.png",
      width: 1200,
      height: 630,
    },
  ]);
});

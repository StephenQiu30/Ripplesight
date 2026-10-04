import type { NextConfig } from "next";

import { loadRootWebEnvironment } from "./env.config.mjs";

loadRootWebEnvironment();

const nextConfig: NextConfig = {
  agentRules: false,
  devIndicators: false,
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  allowedDevOrigins: ["127.0.0.1"],
  async rewrites() {
    const exports = [
      "/public/feed.xml",
      "/public/feed/full.xml",
      "/public/feed/all.xml",
      "/public/feed/:kind.xml",
      "/public/feed/category/:category.xml",
      "/public/feed/full/category/:category.xml",
      "/public/items/:id.md",
      "/public/selected.md",
      "/public/reports/:kind/:key.md",
      "/public/agent.md",
      "/public/api/:path*",
      "/public/mcp",
      "/feed.xml",
      "/feed/full.xml",
      "/feed/all.xml",
      "/feed/:kind.xml",
      "/feed/category/:category.xml",
      "/feed/full/category/:category.xml",
      "/items/:id.md",
      "/items/:id.jsonld",
      "/items/:id/poster.svg",
      "/selected.md",
      "/reports/:kind/:key.md",
      "/reports/:kind/:key/poster.svg",
      "/events/:id/poster.svg",
      "/llms.txt",
      "/agent.md",
      "/hotkey-indexnow-key.txt",
      "/og/site.png",
      "/og/pages/:page.png",
      "/og/items/:id.png",
      "/og/posters/:id.png",
      "/og/stories/:id.png",
      "/og/posters/stories/:id.png",
      "/og/reports/:kind/:key.png",
      "/og/posters/reports/:kind/:key.png",
      "/og/topics/:slug.png",
      "/mcp",
    ];
    return {
      beforeFiles: exports.map((source) => ({
        source,
        destination: `/api/__exports${source}`,
      })),
      afterFiles: [],
      fallback: [],
    };
  },
};

export default nextConfig;

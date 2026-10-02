import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  agentRules: false,
  devIndicators: false,
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  allowedDevOrigins: ["127.0.0.1"],
  async rewrites() {
    const exports = [
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
      "/robots.txt",
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
      "/sitemap.xml",
      "/sitemaps/items-:shard.xml",
      "/sitemaps/stories-:shard.xml",
      "/sitemaps/reports-:shard.xml",
      "/sitemaps/topics-:shard.xml",
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

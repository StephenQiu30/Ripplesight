import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Ripplesight",
    short_name: "Ripplesight",
    description:
      "Ripplesight：公开资讯阅读与个人舆情监控，沿着来源、讨论与事件进展追踪变化。个人非商业使用。",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#171717",
    icons: [
      {
        src: "/icon.png?v=2",
        sizes: "256x256",
        type: "image/png",
        purpose: "any",
      },
    ],
  };
}

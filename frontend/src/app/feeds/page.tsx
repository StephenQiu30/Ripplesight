import type { Metadata } from "next";
import { connection } from "next/server";

import {
  categories,
  PublicationNavigation,
} from "@/components/publication/reading-parts";

export const metadata: Metadata = {
  title: "RSS 订阅",
  robots: { index: false, follow: false },
};

export default async function FeedsPage() {
  await connection();
  const feeds = [
    ["/feed.xml", "精选摘要"],
    ["/feed/full.xml", "精选全文"],
    ["/feed/all.xml", "全部公开摘要"],
    ["/feed/daily.xml", "日报"],
    ["/feed/weekly.xml", "周刊"],
    ["/feed/monthly.xml", "月刊"],
  ];
  return (
    <>
      <PublicationNavigation />
      <div>
        <h1 className="text-3xl font-medium">订阅资讯</h1>
        <p className="text-muted-foreground mt-5 text-sm leading-7">
          复制链接到 RSS
          阅读器。全文订阅只包含有明确再分发许可的正文，其余条目保留摘要和站内阅读入口。
        </p>
        <ul className="mt-8 flex flex-col gap-y-5">
          {feeds.map(([href, label]) => (
            <li key={href} className="flex flex-wrap gap-3">
              <span className="w-24 text-sm">{label}</span>
              <a href={href} className="font-mono text-sm break-all underline">
                {href}
              </a>
            </li>
          ))}
        </ul>
        <h2 className="mt-12 text-lg font-medium">分类精选</h2>
        <ul className="mt-5 flex flex-col gap-y-4">
          {categories.map(([key, label]) => (
            <li key={key} className="flex flex-wrap gap-4 text-sm">
              <span className="w-16">{label}</span>
              <a href={`/feed/category/${key}.xml`} className="underline">
                摘要
              </a>
              <a href={`/feed/full/category/${key}.xml`} className="underline">
                获准全文
              </a>
            </li>
          ))}
        </ul>
        <h2 className="mt-12 text-lg font-medium">其他格式</h2>
        <p className="mt-5 flex flex-wrap gap-5 text-sm">
          <a href="/selected.md" className="underline">
            精选 Markdown
          </a>
          <a href="/agent" className="underline">
            API / MCP 接入
          </a>
        </p>
      </div>
    </>
  );
}

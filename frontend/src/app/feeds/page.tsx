import * as UI from "@/components/ui/content";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
import type { Metadata } from "next";
import { connection } from "next/server";

import { categories } from "@/components/publication/reading-parts";

export const metadata: Metadata = {
  title: "RSS 订阅",
  robots: { index: false, follow: false },
};

export default async function FeedsPage() {
  await connection();
  const feeds = [
    ["/public/feed.xml", "精选摘要"],
    ["/public/feed/full.xml", "精选全文"],
    ["/public/feed/all.xml", "全部公开摘要"],
    ["/public/feed/daily.xml", "日报"],
    ["/public/feed/weekly.xml", "周刊"],
    ["/public/feed/monthly.xml", "月刊"],
  ];
  return (
    <>
      <UI.Content>
        <UI.Heading level={1} className="text-3xl font-medium">
          订阅资讯
        </UI.Heading>
        <UI.Text className="text-muted-foreground mt-5 text-sm leading-7">
          复制链接到 RSS
          阅读器。订阅读取服务器明确设置的发布账号，未设置时保持未发布。全文订阅只包含有明确再分发许可的正文，其余条目保留摘要和站内阅读入口。每个订阅最多50项，公开接口共享每60秒120次的访问额度。
        </UI.Text>
        <ItemGroup className="mt-8 flex flex-col gap-y-5">
          {feeds.map(([href, label]) => (
            <Item
              role="listitem"
              variant="default"
              key={href}
              className="flex flex-wrap gap-3"
            >
              <ItemContent className="min-w-0 gap-3">
                <UI.Text as="span" className="w-24 text-sm">
                  {label}
                </UI.Text>
                <UI.TextLink
                  href={href}
                  className="font-mono text-sm break-all underline"
                >
                  {href}
                </UI.TextLink>
              </ItemContent>
            </Item>
          ))}
        </ItemGroup>
        <UI.Heading level={2} className="mt-12 text-lg font-medium">
          分类精选
        </UI.Heading>
        <ItemGroup className="mt-5 flex flex-col gap-y-4">
          {categories.map(([key, label]) => (
            <Item
              role="listitem"
              variant="default"
              key={key}
              className="flex flex-wrap gap-4"
            >
              <ItemContent className="min-w-0 gap-3">
                <UI.Text as="span" className="w-16">
                  {label}
                </UI.Text>
                <UI.TextLink
                  href={`/public/feed/category/${key}.xml`}
                  className="underline"
                >
                  摘要
                </UI.TextLink>
                <UI.TextLink
                  href={`/public/feed/full/category/${key}.xml`}
                  className="underline"
                >
                  获准全文
                </UI.TextLink>
              </ItemContent>
            </Item>
          ))}
        </ItemGroup>
        <UI.Heading level={2} className="mt-12 text-lg font-medium">
          其他格式
        </UI.Heading>
        <UI.Text className="mt-5 flex flex-wrap gap-5 text-sm">
          <UI.TextLink href="/public/selected.md" className="underline">
            精选 Markdown
          </UI.TextLink>
          <UI.TextLink href="/agent" className="underline">
            API / MCP 接入
          </UI.TextLink>
        </UI.Text>
      </UI.Content>
    </>
  );
}

import type { Metadata } from "next";
import { connection } from "next/server";

import { getPublicAgentMarkdown } from "@/api/gongkaifenfa";
import {
  PublicationNavigation,
  PublicationFailure,
  publicationApiOptions,
} from "@/components/publication/reading-parts";

export const metadata: Metadata = {
  title: "Agent 接入",
  robots: { index: false, follow: false },
};

export default async function AgentPage() {
  await connection();
  let instructions: string;
  try {
    instructions = await getPublicAgentMarkdown(publicationApiOptions);
  } catch (error) {
    return (
      <>
        <PublicationNavigation />
        <PublicationFailure error={error} href="/agent" />
      </>
    );
  }
  const tools = [
    ["hotkey_get_latest", "精选或全部资讯，24 小时 / 7 天"],
    ["hotkey_search", "字面检索可公开的标题、摘要和获准全文"],
    ["hotkey_get_hot_topics", "当前来源热度与公开事件"],
    ["hotkey_get_story", "事件的完整可公开报道"],
    ["hotkey_get_daily", "已生成且固定许可仍有效的日报"],
  ];
  return (
    <>
      <PublicationNavigation />
      <main className="mx-auto max-w-4xl px-5 py-10 sm:px-8">
        <h1 className="text-3xl font-medium">让 Agent 读取资讯</h1>
        <p className="text-muted-foreground mt-5 text-sm leading-7">
          MCP 使用同站 /mcp 的 HTTP POST 接入；API、RSS 与 Markdown
          读取相同发布投影。读取不会抓取外站、调用模型或执行写入。
        </p>
        <h2 className="mt-10 text-lg font-medium">五个只读工具</h2>
        <dl className="mt-5 space-y-5">
          {tools.map(([name, description]) => (
            <div key={name}>
              <dt className="font-mono text-sm break-all">{name}</dt>
              <dd className="text-muted-foreground mt-1 text-sm">
                {description}
              </dd>
            </div>
          ))}
        </dl>
        <p className="text-muted-foreground mt-8 text-sm leading-7">
          常规查询只有 24 小时和 7 天窗口。完整精选同步另用 snapshot + epoch +
          changes
          接口；模型榜通过网页查看。单篇正文是否可以再分发由该来源的许可决定。
        </p>
        <p className="mt-6 flex flex-wrap gap-5 text-sm">
          <a className="underline" href="/llms.txt">
            llms.txt
          </a>
          <a className="underline" href="/agent.md">
            完整 Markdown 说明
          </a>
          <a
            className="underline"
            href="/api/publication/selected/snapshot"
            download
          >
            精选同步快照
          </a>
        </p>
        <details className="mt-10">
          <summary className="cursor-pointer text-sm font-medium">
            查看当前服务说明
          </summary>
          <pre className="bg-muted mt-4 overflow-x-auto rounded-md p-5 text-xs leading-6 break-words whitespace-pre-wrap">
            {instructions}
          </pre>
        </details>
      </main>
    </>
  );
}

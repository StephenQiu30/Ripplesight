import { ChevronDownIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import type { Metadata } from "next";
import { connection } from "next/server";

import { getPublisherAgentInstructions } from "@/api/gongkaifenfa";
import { SelectedSnapshotDownload } from "@/app/agent/components/selected-snapshot-download";
import {
  PublicationNavigation,
  PublicationFailure,
} from "@/components/publication/reading-parts";

export const metadata: Metadata = {
  title: "Agent 接入",
  robots: { index: false, follow: false },
};

export default async function AgentPage() {
  await connection();
  let instructions: string;
  try {
    instructions = await getPublisherAgentInstructions({});
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
      <div>
        <h1 className="text-3xl font-medium">让 Agent 读取资讯</h1>
        <p className="text-muted-foreground mt-5 text-sm leading-7">
          匿名 MCP 使用同站 /public/mcp 的 HTTP POST
          接入；/public/api/items、RSS 与 Markdown
          读取同一明确发布账号的公开投影，Cookie不会改变该账号。未配置发布账号时保持未发布。读取不会抓取外站、调用模型或执行写入。
        </p>
        <h2 className="mt-10 text-lg font-medium">五个只读工具</h2>
        <dl className="mt-5 flex flex-col gap-y-5">
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
          常规查询只有 24 小时和 7
          天窗口，API每页最多100项，搜索每页最多40项；latest和search支持游标。公开接口共享每60秒120次的访问额度，超限后按Retry-After等待。单篇正文是否可以再分发由该来源的许可决定。原根路径及完整精选同步保留当前登录账号范围；模型榜通过网页查看。
        </p>
        <p className="mt-6 flex flex-wrap gap-5 text-sm">
          <a className="underline" href="/public/agent.md">
            公开接入说明
          </a>
          <a className="underline" href="/agent.md">
            当前账号 Markdown 说明
          </a>
          <SelectedSnapshotDownload />
        </p>
        <Collapsible className="mt-10">
          <CollapsibleTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
            >
              <span className="min-w-0 text-left">查看当前服务说明</span>
              <ChevronDownIcon
                aria-hidden="true"
                data-icon="inline-end"
                className="group-data-[state=open]:rotate-180"
              />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent forceMount className="data-[state=closed]:hidden">
            <pre className="bg-muted mt-4 overflow-x-auto rounded-md p-5 text-xs leading-6 break-words whitespace-pre-wrap">
              {instructions}
            </pre>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </>
  );
}

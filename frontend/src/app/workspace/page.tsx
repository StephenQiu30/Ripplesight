import * as UI from "@/components/ui/content";
import type { Metadata } from "next";
import { connection } from "next/server";
import Link from "next/link";
import { ArrowUpRightIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item";

export const metadata: Metadata = {
  title: "我的工作台",
  robots: { index: false, follow: false },
};

const groups = [
  {
    title: "我的关注与报告",
    description: "设置关注方向，阅读个人资料，生成与管理报告。",
    links: [
      ["/topics", "我的关注", "管理关键词与关注方向"],
      ["/monitors/new", "创建关注", "开始持续关注一个话题"],
      ["/reports", "我的报告", "查看已生成的个人报告"],
      ["/alerts", "突发告警", "配置阈值、冷却并查看评估历史"],
      ["/editions", "编选日周月刊", "提交编选并查看任务进度"],
    ],
  },
  {
    title: "资料与采集",
    description: "查看自己采集的内容与事件，核对来源和执行记录。",
    links: [
      ["/events", "我的事件", "沿着固定资料追踪事件进展"],
      ["/content", "相关内容", "阅读已采集的帖子与讨论"],
      ["/hotlists", "来源热榜", "查看原生榜单和快照"],
      ["/jobs", "采集记录", "检查进度、覆盖与失败原因"],
      ["/sources", "来源设置", "管理连接与来源授权"],
      ["/editorial-sources", "编辑来源", "管理资讯来源和材料"],
    ],
  },
  {
    title: "发布与管理",
    description: "运营操作继续校验独立权限，发送通知需要登录并配置投递渠道。",
    links: [
      ["/publication/manage", "发布管理", "管理公开许可、发布与撤回"],
      ["/operations", "运营与通知", "设置周报通知和投递渠道"],
      ["/operations/models", "模型配置", "查看能力、用量与预算"],
      ["/site/manage", "站点设置", "维护公开联系资料"],
      ["/codex-resets", "Codex 公告", "查看本账户的公告监控"],
      ["/codex-resets/manage", "公告管理", "管理公告扫描配置"],
      ["/feeds", "RSS 订阅", "查看认证后可用的订阅出口"],
      ["/agent", "Agent 接入", "查看认证后的数据接入方式"],
      ["/feedback", "反馈", "提交问题与改进建议"],
      ["/account", "账户设置", "管理资料与登录凭据"],
    ],
  },
];

export default async function WorkspacePage() {
  await connection();
  return (
    <UI.Content className="flex flex-col gap-10">
      <UI.Content className="flex flex-wrap items-start justify-between gap-5">
        <UI.Content>
          <UI.Heading level={1} className="text-3xl font-medium tracking-tight">
            我的工作台
          </UI.Heading>
          <UI.Text className="text-muted-foreground mt-4 leading-7">
            个人关注、报告与管理功能，从这里继续。
          </UI.Text>
        </UI.Content>
        <Button asChild variant="outline">
          <Link href="/">返回信息首页</Link>
        </Button>
      </UI.Content>
      {groups.map((group) => (
        <UI.Content as="section" key={group.title} aria-label={group.title}>
          <UI.Heading level={2} className="text-xl font-medium">
            {group.title}
          </UI.Heading>
          <UI.Text className="text-muted-foreground mt-2 text-sm leading-6">
            {group.description}
          </UI.Text>
          <ItemGroup className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {group.links.map(([href, title, description]) => (
              <Item role="listitem" key={href} variant="muted">
                <Link
                  href={href}
                  className="flex w-full min-w-0 items-start justify-between gap-4"
                >
                  <ItemContent>
                    <ItemTitle>{title}</ItemTitle>
                    <ItemDescription>{description}</ItemDescription>
                  </ItemContent>
                  <ArrowUpRightIcon aria-hidden="true" />
                </Link>
              </Item>
            ))}
          </ItemGroup>
        </UI.Content>
      ))}
    </UI.Content>
  );
}

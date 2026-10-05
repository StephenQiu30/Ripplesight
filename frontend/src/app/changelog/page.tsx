import * as UI from "@/components/ui/content";
import { connection } from "next/server";
import { InformationPage } from "@/components/site/information-page";
import { welcomeMetadata } from "@/components/site/welcome-metadata";

export const metadata = welcomeMetadata(
  "/changelog",
  "变更记录",
  "查看知微见澜公开欢迎页、登录和信息监控工作区的更新记录。",
);
export default async function ChangelogPage() {
  await connection();
  return (
    <InformationPage title="变更记录">
      <UI.Heading level={2} className="text-foreground text-lg font-medium">
        2026-10-02 · 欢迎页与个人工作区
      </UI.Heading>
      <UI.Text>
        首页作为公开产品介绍页，登录后进入业务工作区。账号密码、GitHub
        与邮箱验证码共用账户会话，所有页面沿用统一布局、字体与固定头尾。
      </UI.Text>
      <UI.Heading level={2} className="text-foreground text-lg font-medium">
        2026-10-02 · 全量业务移植进行中
      </UI.Heading>
      <UI.Text>
        保留 Python、Next.js 与
        Kafka，接入精选分析、中文阅读、事实纠错与热度、日周月刊、模型榜、Codex
        公告、统一公开分发、运营与通知。逐项功能和故障恢复仍在汇合验证，不代表真实渠道或持续运行验收通过。
      </UI.Text>
      <UI.Heading level={2} className="text-foreground text-lg font-medium">
        2026-10-01 · Demo 与页面重建
      </UI.Heading>
      <UI.Text>
        移除产品登录与注册要求，重建监控、来源、内容、热榜、任务与报告入口，保留来源授权、预算及证据合同。原有产品验收责任继续保留。
      </UI.Text>
    </InformationPage>
  );
}

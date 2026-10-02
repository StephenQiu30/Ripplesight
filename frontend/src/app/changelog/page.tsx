import type { Metadata } from "next";
import { connection } from "next/server";
import { InformationPage } from "@/components/site/information-page";

export const metadata: Metadata = {
  title: "变更记录",
  robots: { index: false, follow: false },
};
export default async function ChangelogPage() {
  await connection();
  return (
    <InformationPage title="变更记录">
      <h2 className="text-foreground text-lg font-medium">
        2026-10-02 · 全量业务移植进行中
      </h2>
      <p>
        保留 Python、Next.js 与
        Kafka，接入精选分析、中文阅读、事实纠错与热度、日周月刊、模型榜、Codex
        公告、统一公开分发、运营与通知。逐项功能和故障恢复仍在汇合验证，不代表真实渠道或持续运行验收通过。
      </p>
      <h2 className="text-foreground text-lg font-medium">
        2026-10-01 · Demo 与页面重建
      </h2>
      <p>
        移除产品登录与注册要求，重建监控、来源、内容、热榜、任务与报告入口，保留来源授权、预算及证据合同。原有产品验收责任继续保留。
      </p>
    </InformationPage>
  );
}

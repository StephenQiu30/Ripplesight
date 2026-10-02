import type { Metadata } from "next";
import { connection } from "next/server";

import { InformationPage } from "@/components/site/information-page";
import { SiteOverview } from "./components/site-overview";

export const metadata: Metadata = {
  title: "关于 HotKey",
  robots: { index: false, follow: false },
};

export default async function AboutPage() {
  await connection();
  return (
    <InformationPage title="关于 HotKey">
      <p>
        HotKey
        将监控主题、来源材料、评论、原生热榜与事件进展放在同一个可追溯的工作区。公开资讯、行业主题、日周月刊、模型榜与公告使用各自的版本和证据。
      </p>
      <p>
        当前 Demo
        无产品账户，运营入口采用独立令牌。功能启用、代码验证与真实来源效果分别记录；当前读到的统计只计算有许可且仍可见的资料。
      </p>
      <SiteOverview />
    </InformationPage>
  );
}

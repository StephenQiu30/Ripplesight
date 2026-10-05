import * as UI from "@/components/ui/content";
import { connection } from "next/server";

import { InformationPage } from "@/components/site/information-page";
import { welcomeMetadata } from "@/components/site/welcome-metadata";

export const metadata = welcomeMetadata(
  "/about",
  "关于知微见澜",
  "了解知微见澜如何沿着来源、讨论和事件进展，帮助你持续关注在意的话题。",
);

export default async function AboutPage() {
  await connection();
  return (
    <InformationPage title="关于知微见澜">
      <UI.Text>
        知微见澜
        将监控主题、来源材料、评论、原生热榜与事件进展放在同一个可追溯的工作区。公开资讯、行业主题、日周月刊、模型榜与公告使用各自的版本和证据。
      </UI.Text>
      <UI.Text>
        首页提供产品介绍与使用说明。登录后进入信息工作区，管理个人关注、阅读相关内容，沿着来源与时间理解变化。
      </UI.Text>
      <UI.Text>
        支持账号密码、GitHub
        和邮箱验证码登录。来源许可、模型分析与真实采集状态分别展示，功能实现不代替持续运行与真实来源验收。
      </UI.Text>
    </InformationPage>
  );
}

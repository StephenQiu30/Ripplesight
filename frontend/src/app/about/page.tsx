import * as UI from "@/components/ui/content";
import { connection } from "next/server";

import { InformationPage } from "@/components/site/information-page";
import { welcomeMetadata } from "@/components/site/welcome-metadata";

export const metadata = welcomeMetadata(
  "/about",
  "关于 Ripplesight",
  "了解 Ripplesight 如何沿着来源、讨论和事件进展，帮助你持续关注在意的话题。",
);

export default async function AboutPage() {
  await connection();
  return (
    <InformationPage title="关于 Ripplesight">
      <UI.Text>
        Ripplesight
        是面向个人非商业使用的公开资讯阅读与舆情监控项目。围绕关键词连接来源材料、讨论与事件进展，让正在发生的变化有依据、可追溯。
      </UI.Text>
      <UI.Text>
        首页用于公开资讯阅读。登录后进入个人工作区，配置关注主题、阅读相关内容和已有报告，沿着来源与时间理解变化。
      </UI.Text>
      <UI.Text>
        支持账号密码、GitHub
        和邮箱验证码登录。来源许可、模型分析与真实采集状态分别展示，功能实现不代替持续运行与真实来源验收。
      </UI.Text>
    </InformationPage>
  );
}

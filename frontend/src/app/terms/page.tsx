import * as UI from "@/components/ui/content";
import { connection } from "next/server";
import { InformationPage } from "@/components/site/information-page";
import { welcomeMetadata } from "@/components/site/welcome-metadata";

export const metadata = welcomeMetadata(
  "/terms",
  "使用与内容许可",
  "了解Ripplesight的信息使用范围、来源追溯与内容再分发许可。",
);
export default async function TermsPage() {
  await connection();
  return (
    <InformationPage title="使用与内容许可">
      <UI.Text>
        Ripplesight
        用于信息监控、来源追溯和受控验证。页面结果保留来源链接；模型生成的标题、摘要、译文和事件关系可能需要人工核对，预测时间不表示额度已到账。
      </UI.Text>
      <UI.Text>
        源码许可与内容许可分别适用。AIHOT 移植源码的 MIT 版权和出处保存在仓库
        LICENSE；来源正文、图像、标识及数据不因代码许可自动获得再分发权限。
      </UI.Text>
      <UI.Text>
        摘要、站内全文与全文再分发各有独立许可。下载、RSS、API、MCP
        和海报都读取当前已授权版本；不能据此绕过原站访问限制或将未许可材料再发布。
      </UI.Text>
      <UI.Text>
        来源、模型与渠道必须经过相应授权和预算准入。当前
        X、付费模型及外部发送的暂停条件仍有效；B
        站试点仅限本人个人、非商业研究，不扩大到其他账号或平台。
      </UI.Text>
    </InformationPage>
  );
}

import * as UI from "@/components/ui/content";
import { connection } from "next/server";
import { InformationPage } from "@/components/site/information-page";
import { welcomeMetadata } from "@/components/site/welcome-metadata";

export const metadata = welcomeMetadata(
  "/privacy",
  "隐私与本机数据",
  "了解账户、登录会话、本机阅读记录与反馈资料的保存方式。",
);
export default async function PrivacyPage() {
  await connection();
  return (
    <InformationPage title="隐私与本机数据">
      <UI.Text>
        账号密码、GitHub
        和邮箱验证码登录使用同一账户会话。密码只保存哈希，登录会话通过 HttpOnly
        Cookie 保存；GitHub
        授权用于核对身份，邮箱验证码有有效期与使用次数限制，不用于订阅或报告投递。
      </UI.Text>
      <UI.Text>
        个人关注和任务按账户区分。退出会撤销当前登录会话；修改登录凭据会撤销已有会话，需重新登录。来源凭据和独立运营令牌用于相应业务，不作为个人登录密码。
      </UI.Text>
      <UI.Text>
        收藏、已读、阅读位置及反馈草稿保存在当前浏览器。清除浏览器站点数据会删除这些记录；它们不自动同步到其他设备。导入导出只包含页面声明的本机字段，不包含原始全文或服务端凭据。
      </UI.Text>
      <UI.Text>
        提交反馈会将文字、可选联系信息、页面地址及图片保存到服务端。来源标识以
        HMAC 处理用于冷却和封禁，不把原始 IP
        或浏览器标识保存到反馈记录；运营处理者可以查看和删除反馈内容及附件，保留必要的操作审计。
      </UI.Text>
      <UI.Text>
        许可收紧或材料撤回后，新读取会重新检查可见性。已下载的文件、RSS
        阅读器副本和用户保存的本机内容无法由服务端远程删除。不要在反馈中提交密码、令牌或敏感个人资料。
      </UI.Text>
    </InformationPage>
  );
}

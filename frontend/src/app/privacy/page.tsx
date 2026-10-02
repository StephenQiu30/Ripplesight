import type { Metadata } from "next";
import { connection } from "next/server";
import { InformationPage } from "@/components/site/information-page";

export const metadata: Metadata = {
  title: "隐私与本机数据",
  robots: { index: false, follow: false },
};
export default async function PrivacyPage() {
  await connection();
  return (
    <InformationPage title="隐私与本机数据">
      <p>
        当前 Demo
        不建立产品账户、登录会话或第三方登录。来源凭据和运营令牌有独立用途；运营令牌仅保存在当前页面内存。
      </p>
      <p>
        收藏、已读、阅读位置、笔记及反馈草稿保存在当前浏览器。清除浏览器站点数据会删除这些记录；它们不自动同步到其他设备。导入导出只包含页面声明的本机字段，不包含原始全文或服务端凭据。
      </p>
      <p>
        提交反馈会将文字、可选联系信息、页面地址及图片保存到服务端。来源标识以
        HMAC 处理用于冷却和封禁，不把原始 IP
        或浏览器标识保存到反馈记录；运营处理者可以查看和删除反馈内容及附件，保留必要的操作审计。
      </p>
      <p>
        许可收紧或材料撤回后，新读取会重新检查可见性。已下载的文件、RSS
        阅读器副本和用户保存的本机内容无法由服务端远程删除。不要在反馈中提交密码、令牌或敏感个人资料。
      </p>
    </InformationPage>
  );
}

import * as UI from "@/components/ui/content";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import type { ReactNode } from "react";

import { BasicLayout } from "@/layout/basic-layout";
import { layoutFontClassName } from "@/layout/layout-fonts";
import { readLayoutSession } from "@/components/auth/layout-session";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "知微见澜 Ripplesight · 从一个关键词，看见正在发生的变化",
    template: "%s · 知微见澜 Ripplesight",
  },
  description:
    "设定你关心的品牌、产品或话题，持续汇集相关讨论，沿着来源和时间看清变化如何发生。",
  applicationName: "知微见澜 Ripplesight",
  robots: { index: false, follow: false },
};

export default async function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  const session = await readLayoutSession();
  // shadcn Sidebar 把展开状态写在 sidebar_state cookie；没有记录时默认展开。
  const sidebarOpen = (await cookies()).get("sidebar_state")?.value !== "false";
  return (
    <UI.DocumentRoot
      lang="zh-CN"
      data-scroll-behavior="smooth"
      className={layoutFontClassName}
    >
      <UI.DocumentBody className="overflow-hidden print:overflow-visible">
        <BasicLayout session={session} sidebarOpen={sidebarOpen}>
          {children}
        </BasicLayout>
      </UI.DocumentBody>
    </UI.DocumentRoot>
  );
}

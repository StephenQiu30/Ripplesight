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
    default: "Ripplesight · 从一个关键词，看见正在发生的变化",
    template: "%s · Ripplesight",
  },
  description:
    "Ripplesight 是面向个人非商业使用的公开资讯阅读与舆情监控项目。围绕关键词连接来源材料、讨论与事件进展，让正在发生的变化有依据、可追溯。",
  applicationName: "Ripplesight",
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

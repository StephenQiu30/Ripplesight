import * as UI from "@/components/ui/content";
import type { Metadata } from "next";
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
  // Browser extensions may add theme attributes before hydration. Limit this
  // exception to <html>; descendants must still report rendering mismatches.
  return (
    <UI.DocumentRoot
      lang="zh-CN"
      data-scroll-behavior="smooth"
      className={layoutFontClassName}
      suppressHydrationWarning
    >
      <UI.DocumentBody className="overflow-hidden print:overflow-visible">
        <BasicLayout session={session}>{children}</BasicLayout>
      </UI.DocumentBody>
    </UI.DocumentRoot>
  );
}

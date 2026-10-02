import type { Metadata } from "next";
import type { ReactNode } from "react";

import { LocalThemeInitializer } from "@/components/publication/local-reading";
import { BasicLayout } from "@/layout/basic-layout";
import { layoutFontClassName } from "@/layout/layout-fonts";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "知微见澜 Ripplesight · 从一个关键词，看见正在发生的变化",
    template: "%s · 知微见澜 Ripplesight",
  },
  description:
    "设定你关心的品牌、产品或话题，持续汇集相关讨论，沿着来源和时间看清变化如何发生。",
  applicationName: "知微见澜 Ripplesight",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="zh-CN"
      data-scroll-behavior="smooth"
      className={layoutFontClassName}
    >
      <body className="overflow-hidden print:overflow-visible">
        <LocalThemeInitializer />
        <BasicLayout>{children}</BasicLayout>
      </body>
    </html>
  );
}

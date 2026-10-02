import { connection } from "next/server";

import { HomeContent } from "@/app/components/home-content";
import { welcomeMetadata } from "@/components/site/welcome-metadata";

export const metadata = {
  ...welcomeMetadata(
    "/",
    "知微见澜 Ripplesight",
    "设定你关心的品牌、产品或话题，持续汇集相关讨论，沿着来源和时间看清变化如何发生。",
  ),
  title: {
    absolute: "知微见澜 Ripplesight · 从一个关键词，看见正在发生的变化",
  },
};

export default async function Home() {
  await connection();

  return <HomeContent />;
}

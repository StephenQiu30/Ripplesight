import { connection } from "next/server";

import { HomeContent, type HomeReading } from "@/app/components/home-content";
import {
  getPublicHotStories,
  getPublicTopicDirectory,
  listPublicItems,
} from "@/api/gongkaifabu";
import { listPublicEditionCatalogue } from "@/api/gongkaikanwumulu";
import { welcomeMetadata } from "@/components/site/welcome-metadata";
import { ApiRequestError } from "@/request";

export const metadata = {
  ...welcomeMetadata(
    "/",
    "知微见澜 Ripplesight",
    "公开阅读最新资讯、事件脉络、行业专题与模型评测，登录后配置个人关注、查看已有报告。",
  ),
  title: { absolute: "知微见澜 Ripplesight · 开放的信息平台" },
};

export default async function Home() {
  await connection();
  const results = await Promise.allSettled([
    listPublicItems({ mode: "all", window: "7d", limit: 8 }),
    getPublicHotStories({ limit: 4 }),
    getPublicTopicDirectory(),
    listPublicEditionCatalogue({ kind: "weekly", limit: 2 }),
  ]);
  const reading: HomeReading = {
    items: results[0].status === "fulfilled" ? results[0].value.items : [],
    stories: results[1].status === "fulfilled" ? results[1].value.stories : [],
    topics: results[2].status === "fulfilled" ? results[2].value.topics : [],
    editions: results[3].status === "fulfilled" ? results[3].value.entries : [],
    unavailable: results.flatMap((result, index) =>
      result.status === "rejected" &&
      !(
        result.reason instanceof ApiRequestError &&
        result.reason.code === "publication_not_configured"
      )
        ? [["items", "stories", "topics", "editions"][index]]
        : [],
    ),
  };
  return <HomeContent reading={reading} />;
}

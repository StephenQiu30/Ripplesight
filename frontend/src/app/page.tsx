import { connection } from "next/server";
import { Suspense } from "react";

import { HomeLoading } from "@/app/components/home-loading";

import { HomeContent, type HomeReading } from "@/app/components/home-content";
import {
  getPublicHotStories,
  getPublicTopicDirectory,
  listPublicItems,
} from "@/api/gongkaifabu";
import { listPublicEditionCatalogue } from "@/api/gongkaikanwumulu";
import { welcomeMetadata } from "@/components/site/welcome-metadata";
import { ApiRequestError } from "@/request";
import { categories } from "@/components/publication/reading-parts";

export const metadata = {
  ...welcomeMetadata(
    "/",
    "知微见澜 Ripplesight",
    "公开阅读最新资讯、事件脉络、行业专题与模型评测，登录后配置个人关注、查看已有报告。",
  ),
  title: { absolute: "知微见澜 Ripplesight · 开放的信息平台" },
};

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string; category?: string; cursor?: string }>;
}) {
  await connection();
  const params = await searchParams;
  const mode = params.mode === "selected" ? "selected" : "all";
  const category = categories.find(([key]) => key === params.category)?.[0];
  const cursor = typeof params.cursor === "string" ? params.cursor : undefined;
  return (
    <Suspense fallback={<HomeLoading />}>
      <HomeReadingPage mode={mode} category={category} cursor={cursor} />
    </Suspense>
  );
}

async function HomeReadingPage({
  mode,
  category,
  cursor,
}: {
  mode: "all" | "selected";
  category?: HotKeyAPI.PublicItemView["category"];
  cursor?: string;
}) {
  const results = await Promise.allSettled([
    listPublicItems({ mode, category, cursor, window: "7d", limit: 20 }),
    getPublicHotStories({ limit: 4 }),
    getPublicTopicDirectory(),
    listPublicEditionCatalogue({ limit: 2 }),
  ]);
  const failures = Object.fromEntries(
    results.flatMap((result, index) => {
      if (
        result.status !== "rejected" ||
        (result.reason instanceof ApiRequestError &&
          result.reason.code === "publication_not_configured")
      )
        return [];
      const known =
        result.reason instanceof ApiRequestError ? result.reason : null;
      return [
        [
          ["items", "stories", "topics", "editions"][index],
          { code: known?.code, status: known?.status },
        ],
      ];
    }),
  );
  const reading: HomeReading = {
    observedAt: new Date().toISOString(),
    failures,
    items: results[0].status === "fulfilled" ? results[0].value.items : [],
    sourceStatus:
      results[0].status === "fulfilled"
        ? (results[0].value.source_status ?? [])
        : [],
    stories: results[1].status === "fulfilled" ? results[1].value.stories : [],
    topics: results[2].status === "fulfilled" ? results[2].value.topics : [],
    editions: results[3].status === "fulfilled" ? results[3].value.entries : [],
    nextCursor:
      results[0].status === "fulfilled" ? results[0].value.next_cursor : null,
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
  return (
    <HomeContent
      reading={reading}
      mode={mode}
      category={category}
      cursor={cursor}
    />
  );
}

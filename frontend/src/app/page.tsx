import { connection } from "next/server";
import { Suspense } from "react";

import { HomeLoading } from "@/app/components/home-loading";

import { HomeContent, type HomeReading } from "@/app/components/home-content";
import { getPublicHotStories } from "@/api/gongkaifabu";
import { listPublicEditionCatalogue } from "@/api/gongkaikanwumulu";
import { welcomeMetadata } from "@/components/site/welcome-metadata";
import { ApiRequestError } from "@/request";
import { homeCategories } from "./components/home-format";

export const metadata = {
  ...welcomeMetadata(
    "/",
    "Ripplesight",
    "Ripplesight：公开资讯阅读与个人舆情监控，沿着来源、讨论与事件进展追踪变化。个人非商业使用。",
  ),
  title: { absolute: "Ripplesight · 公开资讯阅读与个人舆情监控" },
};

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string; category?: string; cursor?: string }>;
}) {
  await connection();
  const params = await searchParams;
  const category = homeCategories.find(([key]) => key === params.category)?.[0];
  return (
    <Suspense fallback={<HomeLoading />}>
      <HomeReadingPage category={category} />
    </Suspense>
  );
}

async function HomeReadingPage({ category }: { category?: string }) {
  const results = await Promise.allSettled([
    getPublicHotStories({ limit: 50 }),
    listPublicEditionCatalogue({ kind: "daily", limit: 1 }),
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
          ["stories", "editions"][index],
          { code: known?.code, status: known?.status },
        ],
      ];
    }),
  );
  const reading: HomeReading = {
    observedAt: new Date().toISOString(),
    failures,
    stories: results[0].status === "fulfilled" ? results[0].value.stories : [],
    editions: results[1].status === "fulfilled" ? results[1].value.entries : [],
    unavailable: results.flatMap((result, index) =>
      result.status === "rejected" &&
      !(
        result.reason instanceof ApiRequestError &&
        result.reason.code === "publication_not_configured"
      )
        ? [["stories", "editions"][index]]
        : [],
    ),
  };
  return <HomeContent reading={reading} category={category} />;
}

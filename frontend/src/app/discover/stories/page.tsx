import { PageHeader } from "@/components/system/page-header";
import { connection } from "next/server";
import { getPublicHotStories } from "@/api/gongkaifabu";
import { HomeStoryFeed } from "@/app/components/home-feed";
import { PageState } from "@/components/system/page-state";
import { PublicationFailure } from "@/components/publication/reading-parts";
import { Content } from "@/components/ui/content";
import { discoveryFailure } from "../components/discovery-data";

export const metadata = {
  title: "事件",
  robots: { index: false, follow: false },
};
export default async function StoriesPage() {
  await connection();
  const result = await getPublicHotStories({ limit: 20 }).then(
    (data) => ({ data, error: null }),
    (error: unknown) => ({ data: null, error }),
  );
  return (
    <Content layout="stack" className="gap-8">
      <PageHeader
        title={<>事件</>}
        description={<>沿着公开来源，追踪正在发生的 AI 事件。</>}
      />
      {result.data ? (
        result.data.stories.length ? (
          <HomeStoryFeed
            stories={result.data.stories}
            observedAt={new Date().toISOString()}
          />
        ) : (
          <PageState
            headingLevel={2}
            state="empty"
            eyebrow="公开事件"
            title="暂无公开事件"
            description="公开事件发布后将在这里展示。"
          />
        )
      ) : (
        <PublicationFailure
          headingLevel={2}
          error={discoveryFailure(result.error)}
          href="/discover/stories"
        />
      )}
    </Content>
  );
}

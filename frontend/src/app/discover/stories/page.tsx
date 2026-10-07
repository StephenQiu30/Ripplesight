import { connection } from "next/server";
import { getPublicHotStories } from "@/api/gongkaifabu";
import { HomeStoryFeed } from "@/app/components/home-feed";
import { PageState } from "@/components/system/page-state";
import { PublicationFailure } from "@/components/publication/reading-parts";
import { Content, Heading, Text } from "@/components/ui/content";
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
      <Content as="header" layout="stack" className="gap-2">
        <Heading level={1}>事件</Heading>
        <Text tone="muted" size="sm">
          沿着公开来源，追踪正在发生的 AI 事件。
        </Text>
      </Content>
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
            description="事件发布后，会在这里展示最新进展与来源。"
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

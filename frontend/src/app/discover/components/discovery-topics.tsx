import { Fragment } from "react";
import Link from "next/link";
import * as UI from "@/components/ui/content";
import { Button } from "@/components/ui/button";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item";
import { Separator } from "@/components/ui/separator";
import { PageState } from "@/components/system/page-state";
import { ApiRequestError } from "@/request";

export function DiscoveryTopics({
  directory,
  error,
  retryHref,
}: {
  directory: HotKeyAPI.PublicTopicDirectoryView | null;
  error?: unknown;
  retryHref: string;
}) {
  const known = error instanceof ApiRequestError ? error : null;
  return (
    <UI.Content
      as="aside"
      aria-label="按专题浏览"
      layout="stack"
      className="min-w-0"
    >
      <UI.Heading level={2}>按专题浏览</UI.Heading>
      {!directory ? (
        <PageState
          headingLevel={2}
          state="error"
          eyebrow="专题目录"
          title="专题暂不可读"
          description="可以继续阅读搜索结果，或重新读取专题。"
          errorCode={known?.code ?? known?.kind ?? "publication_read_failed"}
          httpStatus={known?.status}
          action={
            <Button asChild variant="outline">
              <Link href={retryHref}>重新读取专题</Link>
            </Button>
          }
        />
      ) : directory.topics.length ? (
        <ItemGroup className="gap-0">
          {directory.topics.map((topic) => (
            <Fragment key={topic.slug}>
              <Separator />
              <Item className="px-0 py-4" role="listitem">
                <ItemContent className="min-w-0 gap-2">
                  <ItemTitle className="line-clamp-none break-words">
                    <UI.TextLink href={`/discover/topics/${topic.slug}`}>
                      {topic.name}
                    </UI.TextLink>
                  </ItemTitle>
                  <ItemDescription className="line-clamp-none break-words">
                    {topic.definition}
                  </ItemDescription>
                  <UI.Text tone="muted" size="xs">
                    <UI.InlineCode>{topic.total}</UI.InlineCode> 篇精选 · 最近
                    30 天 <UI.InlineCode>{topic.recent}</UI.InlineCode> 篇
                  </UI.Text>
                </ItemContent>
              </Item>
            </Fragment>
          ))}
        </ItemGroup>
      ) : (
        <PageState
          headingLevel={2}
          state="empty"
          eyebrow="专题目录"
          title="暂无公开专题"
          description="专题发布后会出现在这里。"
          action={
            <Button asChild variant="outline">
              <Link href="/">阅读今日热点</Link>
            </Button>
          }
        />
      )}
      <Button
        asChild
        variant="outline"
        size="navigation"
        className="self-start"
      >
        <Link href="/discover/topics">全部专题</Link>
      </Button>
    </UI.Content>
  );
}

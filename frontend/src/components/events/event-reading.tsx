import { PageHeader } from "@/components/system/page-header";
import type { ReactNode } from "react";
import * as UI from "@/components/ui/content";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import { Empty, EmptyDescription, EmptyHeader } from "@/components/ui/empty";
import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/request";
import {
  eventSourceAnchor,
  eventTime,
  type EventSource,
  type RepresentativeComment,
  type TimelineEntry,
} from "./reading-model";

export function EventHeader({
  title,
  firstSeenAt,
  firstSeenBasis,
  updatedAt,
  sourceCount,
  heat,
  revision,
  phase,
  href,
  actions,
}: {
  title: string;
  firstSeenAt: string;
  firstSeenBasis?: "published" | "discovered";
  updatedAt?: string | null;
  sourceCount: number;
  heat?: number | null;
  revision: number;
  phase?: "active" | "watching" | "settled";
  href: string;
  actions?: ReactNode;
}) {
  return (
    <PageHeader
      title={title}
      actions={actions}
      breadcrumbs={[{ label: "事件", href }, { label: "事件详情" }]}
    >
      <UI.Content className="flex flex-wrap gap-x-5 gap-y-2">
        <UI.Text size="xs" tone="muted">
          首次{firstSeenBasis === "published" ? "发布" : "发现"}{" "}
          <UI.InlineCode>
            <UI.Timestamp dateTime={firstSeenAt}>
              {eventTime(firstSeenAt)}
            </UI.Timestamp>
          </UI.InlineCode>
        </UI.Text>
        <UI.Text size="xs" tone="muted">
          {updatedAt ? (
            <>
              最近更新{" "}
              <UI.InlineCode>
                <UI.Timestamp dateTime={updatedAt}>
                  {eventTime(updatedAt)}
                </UI.Timestamp>
              </UI.InlineCode>
            </>
          ) : (
            "事件更新时间未提供"
          )}
        </UI.Text>
        <UI.Text size="xs" tone="muted">
          <UI.InlineCode>{sourceCount}</UI.InlineCode> 个来源
        </UI.Text>
        <UI.Text size="xs" tone="muted">
          热度{" "}
          <UI.InlineCode>
            {heat == null
              ? "待确定"
              : heat.toLocaleString("zh-CN", { maximumFractionDigits: 1 })}
          </UI.InlineCode>
        </UI.Text>
        <UI.Text size="xs" tone="muted" className="sr-only">
          修订 <UI.InlineCode>{revision}</UI.InlineCode>
          {phase
            ? ` · ${{ active: "持续发展", watching: "观察中", settled: "已收束" }[phase]}`
            : ""}
        </UI.Text>
      </UI.Content>
    </PageHeader>
  );
}

export function EventColumns({
  children,
  aside,
}: {
  children: ReactNode;
  aside: ReactNode;
}) {
  return (
    <UI.Content className="reading-columns min-w-0 items-start">
      <UI.Content className="flex min-w-0 flex-col gap-12">
        {children}
      </UI.Content>
      <UI.Content
        as="aside"
        aria-label="舆情与关联信息"
        className="flex min-w-0 flex-col gap-8"
      >
        <Separator className="lg:hidden" />
        {aside}
      </UI.Content>
    </UI.Content>
  );
}

export function EventEmpty({ children }: { children: ReactNode }) {
  return (
    <Empty className="items-start px-0">
      <EmptyHeader>
        <EmptyDescription>{children}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}

export function EventSectionFailure({
  error,
  title,
  retry,
}: {
  error: unknown;
  title: string;
  retry: () => void;
}) {
  const known = error instanceof ApiRequestError ? error : null;
  return (
    <PageState
      headingLevel={2}
      state={
        known?.status === 401 || known?.status === 403 ? "forbidden" : "error"
      }
      eyebrow="事件读取"
      title={title}
      description="可以重新读取；其他已成功读取的部分仍可阅读。"
      errorCode={known?.code}
      httpStatus={known?.status}
      action={
        <Button variant="outline" onClick={retry}>
          重新读取
        </Button>
      }
    />
  );
}

export function FactSummary({
  title,
  summary,
  sources,
  children,
}: {
  title: string;
  summary?: string | null;
  sources: EventSource[];
  children?: ReactNode;
}) {
  return (
    <Item role="listitem" className="items-start px-0">
      <ItemContent className="min-w-0 gap-3">
        {children}
        <ItemTitle className="line-clamp-none w-full">
          <UI.Heading level={3}>{title}</UI.Heading>
        </ItemTitle>
        {summary ? (
          <UI.Text className="whitespace-pre-wrap">{summary}</UI.Text>
        ) : null}
        <UI.Content
          role="group"
          className="flex flex-wrap gap-2"
          aria-label="事实来源引用"
        >
          {sources.map((source) => (
            <UI.TextLink
              key={source.id}
              href={`#${eventSourceAnchor(source.id)}`}
              aria-label={`来源 ${source.number}`}
            >
              <UI.InlineCode>[{source.number}]</UI.InlineCode>
            </UI.TextLink>
          ))}
        </UI.Content>
      </ItemContent>
    </Item>
  );
}

export function EventTimeline({
  entries,
  feedback,
  footer,
  description = "按当前已加载成员的发布时间排列；未提供发布时间时使用观察时间。",
}: {
  entries: TimelineEntry[];
  feedback?: ReactNode;
  footer?: ReactNode;
  description?: string;
}) {
  return (
    <UI.Content
      as="section"
      aria-labelledby="event-timeline-heading"
      className="flex flex-col gap-4"
    >
      <UI.Heading id="event-timeline-heading">时间线</UI.Heading>
      <UI.Text size="xs" tone="muted">
        {description}
      </UI.Text>
      {feedback ??
        (!entries.length ? (
          <EventEmpty>当前事件尚无成员。</EventEmpty>
        ) : (
          <ItemGroup>
            {entries.map((entry) => (
              <UI.Content key={entry.id} className="flex flex-col gap-3">
                <Separator />
                <Item
                  role="listitem"
                  className="flex-nowrap items-start gap-5 px-0"
                >
                  <UI.Text size="xs" tone="muted" className="w-20 shrink-0">
                    <UI.InlineCode>{eventTime(entry.time)}</UI.InlineCode>
                  </UI.Text>
                  <ItemContent className="min-w-0 gap-2">
                    {entry.references ? (
                      <UI.Heading
                        level={3}
                        className="text-sm font-normal md:text-sm"
                      >
                        {entry.title}
                      </UI.Heading>
                    ) : (
                      <UI.TextLink
                        href={`#${eventSourceAnchor(entry.sourceId)}`}
                      >
                        {entry.title}
                      </UI.TextLink>
                    )}
                    <ItemDescription>
                      {entry.source}
                      {entry.reportCount !== undefined
                        ? ` · ${entry.reportCount} 篇公开报道`
                        : ""}
                    </ItemDescription>
                    {entry.references ? (
                      <UI.Content
                        className="flex flex-wrap gap-2"
                        role="group"
                        aria-label="事实来源引用"
                      >
                        {entry.references.map((source) => (
                          <UI.TextLink
                            key={source.id}
                            href={`#${eventSourceAnchor(source.id)}`}
                            aria-label={`来源 ${source.number}`}
                          >
                            <UI.InlineCode>[{source.number}]</UI.InlineCode>
                          </UI.TextLink>
                        ))}
                      </UI.Content>
                    ) : null}
                  </ItemContent>
                </Item>
              </UI.Content>
            ))}
          </ItemGroup>
        ))}
      {footer}
    </UI.Content>
  );
}

export function EventSources({ sources }: { sources: EventSource[] }) {
  return (
    <UI.Content
      as="section"
      aria-labelledby="event-sources-heading"
      className="flex min-w-0 flex-col gap-4"
    >
      <UI.Heading id="event-sources-heading">来源</UI.Heading>
      {!sources.length ? (
        <EventEmpty>当前事件尚无可读来源。</EventEmpty>
      ) : (
        <UI.Content
          role="region"
          aria-label="事件来源表，可横向滚动"
          tabIndex={0}
          className="min-w-0 overflow-x-auto"
        >
          <Table className="min-w-xl">
            <TableCaption>
              编号对应事实引用。
              {sources.some((source) => source.availability === "pending")
                ? "尚未加载的固定来源可通过“加载更多成员”读取。"
                : "可打开站内记录和原文核对。"}
            </TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead>
                <TableHead>来源</TableHead>
                <TableHead>标题</TableHead>
                <TableHead>时间</TableHead>
                <TableHead>互动</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.map((source) => (
                <TableRow
                  id={eventSourceAnchor(source.id)}
                  tabIndex={-1}
                  key={source.id}
                  className="scroll-mt-8"
                >
                  <TableCell>
                    <UI.InlineCode>{source.number}</UI.InlineCode>
                  </TableCell>
                  <TableCell>{source.source}</TableCell>
                  <TableCell className="whitespace-normal">
                    <UI.Content className="flex flex-col gap-2">
                      {source.href ? (
                        <UI.TextLink href={source.href}>
                          {source.title}
                        </UI.TextLink>
                      ) : (
                        <UI.Text>{source.title}</UI.Text>
                      )}
                      {source.originalUrl ? (
                        <UI.TextLink
                          href={source.originalUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          原文
                        </UI.TextLink>
                      ) : null}
                    </UI.Content>
                  </TableCell>
                  <TableCell>
                    <UI.InlineCode>{eventTime(source.time)}</UI.InlineCode>
                  </TableCell>
                  <TableCell>
                    {source.metrics ? (
                      <UI.Content className="flex flex-col gap-1">
                        {(
                          [
                            ["点赞", source.metrics.like_count],
                            ["评论", source.metrics.comment_count],
                            ["转发", source.metrics.repost_count],
                          ] as const
                        ).map(([label, value]) => (
                          <UI.Text size="xs" key={label}>
                            {label}{" "}
                            <UI.InlineCode>
                              {value == null ? "未知" : value}
                            </UI.InlineCode>
                          </UI.Text>
                        ))}
                      </UI.Content>
                    ) : (
                      <UI.Text size="xs" tone="muted">
                        未提供
                      </UI.Text>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </UI.Content>
      )}
    </UI.Content>
  );
}

export function RepresentativeComments({
  comments,
  publicReading = false,
}: {
  comments: RepresentativeComment[];
  publicReading?: boolean;
}) {
  return (
    <UI.Content
      as="section"
      aria-labelledby="event-comments-heading"
      className="flex flex-col gap-4"
    >
      <UI.Heading id="event-comments-heading">代表观点</UI.Heading>
      {publicReading ? (
        <EventEmpty>公开资料暂未提供代表评论。</EventEmpty>
      ) : !comments.length ? (
        <EventEmpty>当前已加载成员尚无代表评论。</EventEmpty>
      ) : (
        <ItemGroup>
          {comments.map((comment) => (
            <Item
              key={comment.id}
              role="listitem"
              className="border-b px-0 py-5"
            >
              <ItemContent className="min-w-0 gap-3">
                <UI.Text size="sm">{comment.source}</UI.Text>
                {comment.state === "none" ? (
                  <UI.Text size="xs" tone="muted">
                    此来源尚无代表评论。
                  </UI.Text>
                ) : comment.state === "unavailable" ? (
                  <UI.Text size="xs" tone="muted">
                    代表评论证据暂不可读。
                  </UI.Text>
                ) : (
                  <>
                    <UI.Quote className="break-words whitespace-pre-wrap">
                      {comment.body ?? "无可读评论正文"}
                    </UI.Quote>
                    <UI.Text size="xs" tone="muted">
                      最新可读观察{" "}
                      <UI.InlineCode>{eventTime(comment.time)}</UI.InlineCode>
                      ；评论未固定到事件成员版本。
                    </UI.Text>
                    {comment.originalUrl ? (
                      <UI.TextLink
                        href={comment.originalUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        评论原文
                      </UI.TextLink>
                    ) : null}
                  </>
                )}
              </ItemContent>
            </Item>
          ))}
        </ItemGroup>
      )}
    </UI.Content>
  );
}

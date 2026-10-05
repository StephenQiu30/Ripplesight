import * as UI from "@/components/ui/content";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import {
  Item,
  ItemContent,
  ItemGroup,
  ItemTitle,
  ItemDescription,
} from "@/components/ui/item";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function beijingTime(value: string | null | undefined): string {
  return value
    ? new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(new Date(value))
    : "暂无记录";
}

const labels: Record<HotKeyAPI.PresentationStatus, string> = {
  announced: "已公告，待确认",
  in_progress: "正在推进",
  confirmed: "已确认",
  expired_unconfirmed: "窗口已过，待确认",
  likely_completed: "推测已完成，待确认",
  withdrawn: "已撤回",
};
const basis: Record<HotKeyAPI.Estimate["basis"], string> = {
  model: "模型估计",
  source: "原话估计",
  source_day: "公告日期估计",
  history: "历史估计",
};

export function ResetTimeline({
  events,
  outage,
}: {
  events: HotKeyAPI.ResetEventView[];
  outage: HotKeyAPI.OutageView | null;
}) {
  return (
    <UI.Content
      as="section"
      aria-label="公告进展"
      className="flex flex-col gap-y-8"
    >
      {outage && (
        <Item variant="muted" asChild>
          <UI.Content as="article" className="p-5">
            <ItemContent className="min-w-0 gap-3">
              <ItemTitle className="line-clamp-none w-full">
                <UI.Heading level={3}>
                  {outage.recovered_at
                    ? "故障后已发布恢复说明"
                    : "有源帖子报告故障"}
                </UI.Heading>
              </ItemTitle>
              <ItemDescription className="mt-2 line-clamp-none leading-6 whitespace-pre-wrap">
                {outage.translation_zh ?? outage.original_text}
              </ItemDescription>
              <Button asChild variant="link" className="px-0">
                <UI.TextLink
                  href={outage.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  阅读故障原帖
                </UI.TextLink>
              </Button>
            </ItemContent>
          </UI.Content>
        </Item>
      )}
      {events.length === 0 && (
        <Empty className="py-8">
          <EmptyHeader>
            <EmptyDescription>当前范围没有公告记录。</EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}
      {events.map((event) => (
        <UI.Content
          as="article"
          key={event.id}
          className="flex flex-col gap-y-4"
        >
          <UI.Content className="flex flex-wrap gap-2">
            <Badge variant="secondary">
              {event.kind === "reset_credit" ? "重置额度" : "直接重置"}
            </Badge>
            <Badge variant="outline">
              {labels[event.presentation_status ?? event.status]}
            </Badge>
            {event.confirmation_basis === "receipt_review" && (
              <Badge variant="outline">人工到账复核</Badge>
            )}
            {event.confirmation_basis === "source_post" && (
              <Badge variant="outline">官方源确认</Badge>
            )}
          </UI.Content>
          <UI.Heading level={3} className="text-lg leading-7 font-medium">
            {event.title || "Codex 重置公告"}
          </UI.Heading>
          {event.scope?.audience_zh && (
            <UI.Text className="text-sm">
              适用范围：{event.scope.audience_zh}
            </UI.Text>
          )}
          {event.scope?.products_zh && (
            <UI.Text className="text-muted-foreground text-sm">
              产品：{event.scope.products_zh}
            </UI.Text>
          )}
          {event.scope?.plans?.length ? (
            <UI.Text className="text-muted-foreground text-sm">
              计划：{event.scope.plans.join("、")}
            </UI.Text>
          ) : null}
          {event.schedule && (
            <UI.Text className="text-sm">
              原话时间：{event.schedule.label}
            </UI.Text>
          )}
          {event.estimate && (
            <UI.Content className="text-muted-foreground flex flex-col gap-y-1 text-sm">
              <UI.Text>{event.estimate.label}</UI.Text>
              <UI.Text>
                {basis[event.estimate.basis]}：{event.estimate.reason}
              </UI.Text>
            </UI.Content>
          )}
          {event.status === "confirmed" && (
            <UI.Text className="text-muted-foreground text-sm">
              {event.confirmation_basis === "source_post"
                ? `确认帖时间：${beijingTime(event.confirmed_at)}`
                : `人工获证日期：${event.occurred_on || "暂无记录"}`}
              。此时间不是账户精确到账时间。
            </UI.Text>
          )}
          <ItemGroup className="flex flex-col gap-y-3">
            {(event.posts ?? []).map((post) => (
              <Item
                role="listitem"
                variant="default"
                key={`${post.post_id}-${post.action}`}
              >
                <ItemContent className="min-w-0 gap-3">
                  <ItemDescription className="line-clamp-none">
                    {beijingTime(post.published_at)} ·{" "}
                    {post.action === "confirm"
                      ? "源确认"
                      : post.action === "withdraw"
                        ? "撤回"
                        : post.action === "amend"
                          ? "公告修订"
                          : post.action === "progress"
                            ? "进展"
                            : "公告"}
                  </ItemDescription>
                  <UI.Text className="mt-1 leading-6 whitespace-pre-wrap">
                    {post.excerpt_zh || post.translation_zh || post.excerpt}
                  </UI.Text>
                  <Button asChild variant="link" className="px-0">
                    <UI.TextLink
                      href={post.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      阅读公告原帖
                    </UI.TextLink>
                  </Button>
                </ItemContent>
              </Item>
            ))}
          </ItemGroup>
        </UI.Content>
      ))}
    </UI.Content>
  );
}

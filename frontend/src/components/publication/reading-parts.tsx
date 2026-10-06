import {
  Item,
  ItemContent,
  ItemGroup,
  ItemDescription,
} from "@/components/ui/item";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import Link from "next/link";

import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ApiRequestError } from "@/request";

import { publicationTime } from "./reading-format";
import { PublicItemFeed } from "./item-feed";
export { categories, publicationTime } from "./reading-format";

export function PublicationFailure({
  error,
  href,
}: {
  error: unknown;
  href: string;
}) {
  const known = error instanceof ApiRequestError ? error : null;
  return (
    <PageState
      state="error"
      errorCode={known?.code}
      httpStatus={known?.status}
      eyebrow="读取未完成"
      title={
        known?.code === "publication_not_configured"
          ? "公开资讯尚未发布"
          : known?.code === "publication_search_busy"
            ? "检索暂时繁忙"
            : known?.status === 404
              ? "这份材料目前不可公开阅读"
              : "暂时无法读取资讯"
      }
      description={
        known?.code === "publication_not_configured"
          ? "公开资料发布后即可阅读，登录后仍可使用个人关注与报告。"
          : known?.code === "publication_search_busy"
            ? "请缩小时间或来源范围，或稍后重新检索。本次没有返回截断结果。"
            : known?.status === 404
              ? "材料不存在、已撤回或许可已经变化。"
              : "请重新加载；读取不会触发来源请求或模型调用。"
      }
      action={
        <Button asChild variant="outline">
          <Link href={href}>重新读取</Link>
        </Button>
      }
    />
  );
}

export function PublicItemCards({
  items,
}: {
  items: HotKeyAPI.PublicItemView[];
}) {
  if (!items.length)
    return (
      <Empty className="py-12">
        <EmptyHeader>
          <EmptyDescription>当前条件下还没有可公开的资讯。</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  return <PublicItemFeed items={items} />;
}

export function PublicSourceStatus({
  sources,
}: {
  sources: HotKeyAPI.PublicSourceStatusView[];
}) {
  const affected = sources.filter(
    (source) =>
      !source.enabled || ["degraded", "failing"].includes(source.health),
  );
  if (!affected.length) return null;
  return (
    <Alert className="mb-5">
      <AlertTitle>部分来源暂未更新</AlertTitle>
      <AlertDescription>
        <ItemGroup className="gap-2">
          {affected.map((source) => (
            <Item
              key={source.source_key}
              role="listitem"
              size="xs"
              className="p-0"
            >
              <ItemContent>
                <ItemDescription className="line-clamp-none">
                  {source.name} ·{" "}
                  {!source.enabled
                    ? "已暂停"
                    : source.health === "failing"
                      ? "采集失败"
                      : "采集不完整"}
                  {" · "}最近成功：{publicationTime(source.last_success_at)}
                </ItemDescription>
              </ItemContent>
            </Item>
          ))}
        </ItemGroup>
        已保存且许可仍有效的资讯可以继续阅读。
      </AlertDescription>
    </Alert>
  );
}

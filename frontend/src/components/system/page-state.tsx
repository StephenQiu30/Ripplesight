import type { ReactNode } from "react";
import { CircleAlertIcon, InboxIcon, LockKeyholeIcon } from "lucide-react";

import * as UI from "@/components/ui/content";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Item, ItemContent } from "@/components/ui/item";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { RetryButton } from "./retry-button";

type PageStateProps = {
  state: "loading" | "empty" | "error" | "forbidden" | "stale";
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
  errorCode?: string;
  httpStatus?: number;
  staleAt?: string;
  loadingLayout?: "list" | "detail";
  /** 整页状态用 1；放在已有页面标题之下的区块状态用 2。 */
  headingLevel?: 1 | 2;
};

function LoadingContent({ layout }: { layout: "list" | "detail" }) {
  const rows = (
    <UI.Content className="flex flex-col gap-6">
      {Array.from({ length: 3 }, (_, index) => (
        <UI.Content key={index} className="flex flex-col gap-4">
          <Separator />
          <Item className="p-0">
            <ItemContent className="gap-3">
              <Skeleton className="h-3 w-1/3 motion-reduce:animate-none" />
              <Skeleton className="h-5 w-11/12 motion-reduce:animate-none" />
              <Skeleton className="h-3 w-3/4 motion-reduce:animate-none" />
              <Skeleton className="h-3 w-1/2 motion-reduce:animate-none" />
            </ItemContent>
          </Item>
        </UI.Content>
      ))}
    </UI.Content>
  );

  return (
    <UI.Content aria-hidden="true" className="flex w-full flex-col gap-8">
      <UI.Content className="flex flex-col gap-4">
        <Skeleton className="h-4 w-24 motion-reduce:animate-none" />
        <Skeleton className="h-8 w-3/4 motion-reduce:animate-none" />
        <Skeleton className="h-4 w-1/2 motion-reduce:animate-none" />
      </UI.Content>
      {layout === "detail" ? (
        <UI.Content className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          <UI.Content className="lg:col-span-2">{rows}</UI.Content>
          <UI.Content className="flex flex-col gap-6">
            <Skeleton className="h-5 w-1/3 motion-reduce:animate-none" />
            <Skeleton className="h-40 w-full motion-reduce:animate-none" />
            <Skeleton className="h-5 w-1/2 motion-reduce:animate-none" />
            <Skeleton className="h-24 w-full motion-reduce:animate-none" />
          </UI.Content>
        </UI.Content>
      ) : (
        rows
      )}
    </UI.Content>
  );
}

export function PageState({
  state,
  eyebrow,
  title,
  description,
  action,
  errorCode,
  httpStatus,
  staleAt,
  loadingLayout = "list",
  headingLevel = 1,
}: PageStateProps) {
  const retry = action ?? <RetryButton />;
  const errorDetails =
    errorCode || httpStatus ? (
      <UI.Text size="xs">
        <UI.InlineCode className="break-all">
          {[errorCode, httpStatus].filter(Boolean).join(" · ")}
        </UI.InlineCode>
      </UI.Text>
    ) : null;

  if (state === "loading")
    return (
      <UI.Content
        role="status"
        aria-label={title}
        aria-busy="true"
        className="w-full py-6"
      >
        <UI.Text className="sr-only">
          {title}。{description}
        </UI.Text>
        <LoadingContent layout={loadingLayout} />
      </UI.Content>
    );

  if (state === "error" || state === "stale")
    return (
      <UI.Content className="flex w-full flex-col gap-4 py-6">
        <Alert
          variant={state === "error" ? "destructive" : "default"}
          role={state === "stale" ? "status" : "alert"}
          aria-label={title}
        >
          <CircleAlertIcon aria-hidden="true" />
          <AlertTitle role="heading" aria-level={headingLevel}>
            <UI.Content className="flex flex-wrap items-center gap-2">
              {state === "stale" && <Badge variant="secondary">已过期</Badge>}
              <UI.Text as="span">{title}</UI.Text>
            </UI.Content>
          </AlertTitle>
          <AlertDescription>
            <UI.Content className="flex flex-col gap-2">
              <UI.Text>{description}</UI.Text>
              {state === "stale" && staleAt && (
                <UI.Text size="xs">
                  数据停留在 <UI.InlineCode>{staleAt}</UI.InlineCode>
                </UI.Text>
              )}
              {errorDetails}
            </UI.Content>
          </AlertDescription>
        </Alert>
        <UI.Content className="flex flex-wrap items-center gap-3">
          {retry}
        </UI.Content>
      </UI.Content>
    );

  const Icon = state === "forbidden" ? LockKeyholeIcon : InboxIcon;
  return (
    <UI.Content
      className="flex flex-1 items-center py-10"
      role="status"
      aria-label={title}
    >
      <Empty>
        <EmptyHeader className="gap-4">
          <UI.Text className="sr-only">{eyebrow}</UI.Text>
          <EmptyMedia>
            <Icon aria-hidden="true" />
          </EmptyMedia>
          <EmptyTitle>
            <UI.Heading level={headingLevel} appearance="sidebar">
              {title}
            </UI.Heading>
          </EmptyTitle>
          <EmptyDescription>{description}</EmptyDescription>
        </EmptyHeader>
        <EmptyContent className="mt-4">
          <UI.Content className="flex flex-wrap justify-center gap-3">
            {action ?? (
              <Button asChild>
                <UI.TextLink
                  href={state === "forbidden" ? "/login" : "/discover?mode=all"}
                >
                  {state === "forbidden" ? "登录" : "探索资讯"}
                </UI.TextLink>
              </Button>
            )}
            {state === "forbidden" && (
              <Button asChild variant="secondary">
                <UI.TextLink href="/">返回首页</UI.TextLink>
              </Button>
            )}
          </UI.Content>
        </EmptyContent>
      </Empty>
    </UI.Content>
  );
}

import * as UI from "@/components/ui/content";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import Link from "next/link";

import { PageState } from "@/components/system/page-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/request";

export function evidenceDate(value: string | null) {
  if (!value) return "未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未知";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function RunStamp({ run }: { run: HotKeyAPI.RunView | null }) {
  return (
    <UI.Content className="text-muted-foreground flex flex-col gap-y-1 text-sm leading-6">
      <UI.Text>
        {run
          ? `发布轮次：${evidenceDate(run.generated_at)}（北京时间）`
          : "尚无已发布轮次；当前展示来源与方法注册表。"}
      </UI.Text>
      {run ? (
        <UI.Text>
          方法{" "}
          <UI.Text as="span" className="font-mono">
            {run.methodology_version}
          </UI.Text>
        </UI.Text>
      ) : null}
      {run?.fx ? (
        <UI.Text>
          人民币换算：1 USD = {run.fx.rate.toFixed(4)} CNY，{run.fx.as_of}{" "}
          {run.fx.source_name}
        </UI.Text>
      ) : null}
    </UI.Content>
  );
}

export function ModelMark({ model }: { model: HotKeyAPI.ModelRefView }) {
  return (
    <Avatar aria-hidden="true">
      <AvatarFallback>{model.brand.monogram}</AvatarFallback>
    </Avatar>
  );
}

function priceAmount(value: number | null, currency: string) {
  if (value === null) return "—";
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency,
    maximumFractionDigits: 4,
  }).format(value);
}

export function OfficialPrice({
  price,
  compact = false,
}: {
  price: HotKeyAPI.PriceView | null;
  compact?: boolean;
}) {
  if (!price)
    return (
      <Empty>
        <EmptyHeader>
          <EmptyDescription>暂无公开价格</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  const hasCny =
    price.cny_input_price !== null || price.cny_output_price !== null;
  const currency = hasCny ? "CNY" : price.currency;
  const input = hasCny ? price.cny_input_price : price.input_price;
  const output = hasCny ? price.cny_output_price : price.output_price;
  const cached = hasCny
    ? price.cny_cached_input_price
    : price.cached_input_price;
  return (
    <UI.Content className="flex flex-col gap-y-1 text-sm leading-6">
      <UI.Text className="font-mono">
        {priceAmount(input, currency)} / {priceAmount(output, currency)}
      </UI.Text>
      {!compact ? (
        <UI.Text>
          输入 / 输出，每百万 token；缓存输入 {priceAmount(cached, currency)}。
        </UI.Text>
      ) : null}
      {!compact && hasCny && price.currency !== "CNY" ? (
        <UI.Text className="text-muted-foreground">
          原价 {priceAmount(price.input_price, price.currency)} /{" "}
          {priceAmount(price.output_price, price.currency)}
          ；人民币金额按本轮汇率换算。
        </UI.Text>
      ) : null}
      <UI.TextLink
        className="text-muted-foreground underline underline-offset-4"
        href={price.source_url}
        target="_blank"
        rel="noreferrer"
      >
        官方价格 · 核对于 {price.verified_on}
      </UI.TextLink>
    </UI.Content>
  );
}

export function SourceStatus({
  source,
}: {
  source: HotKeyAPI.SourceSummaryView;
}) {
  const labels: Record<string, string> = {
    ranked: "参与排名",
    cross_reference: "交叉参考",
    observing: "观察中",
    reference_only: "仅供参考",
    awaiting: "等待成绩",
  };
  return (
    <Badge variant="secondary">{labels[source.status] ?? source.status}</Badge>
  );
}

export function LeaderboardFailure({
  error,
  href,
  resource = false,
}: {
  error: unknown;
  href: string;
  resource?: boolean;
}) {
  const known = error instanceof ApiRequestError ? error : null;
  const absent = resource && known?.status === 404;
  const unavailable = known?.status === 503;
  const description = absent
    ? "该模型或来源没有可读取的公开记录。可以回到榜单或查看来源覆盖。"
    : unavailable
      ? "当前没有可读取的发布结果，或依赖服务暂时不可用。来源和计算规则仍可独立查看。"
      : known?.kind === "timeout"
        ? "本次读取超时，请重新加载。读取不会启动抓取或计算。"
        : known?.kind === "network"
          ? "暂时无法连接榜单服务，请重新加载。"
          : known?.kind === "protocol"
            ? "服务返回的数据不符合约定，请重新加载或检查服务状态。"
            : "本次读取未完成，请重新加载。已有发布结果由服务端保留。";
  return (
    <PageState
      eyebrow={absent ? "未找到" : "读取未完成"}
      title={absent ? "没有这条公开记录" : "暂时无法读取模型榜"}
      description={description}
      action={
        <UI.Content className="flex flex-wrap items-center gap-3">
          {!absent ? (
            <Button asChild>
              <Link href={href}>重新加载</Link>
            </Button>
          ) : null}
          <Button variant="ghost" asChild>
            <Link href="/leaderboard/sources">查看来源</Link>
          </Button>
          {known?.requestId ? (
            <UI.Text className="text-muted-foreground font-mono text-xs">
              请求 ID：{known.requestId}
            </UI.Text>
          ) : null}
        </UI.Content>
      }
    />
  );
}

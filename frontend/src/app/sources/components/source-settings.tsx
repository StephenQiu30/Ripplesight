"use client";
import * as UI from "@/components/ui/content";

import { toast } from "sonner";

import { useCallback, useEffect, useRef, useState } from "react";
import { RotateCcwIcon, XIcon } from "lucide-react";

import { listSourceCapabilities } from "@/api/laiyuannengli";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiRequestError } from "@/request";

import { coverageTime } from "./coverage-window-table";
import { SourceConnectionActions } from "./source-connection-actions";

const STATUS_LABELS: Record<HotKeyAPI.SourcePlatformStatus, string> = {
  unconfigured: "未配置",
  pending_verification: "待验证",
  available: "可用",
  authentication_required: "需重新授权",
  restricted: "受限",
  disabled: "已停用",
  partial: "部分可用",
};

function SourceStatus({ status }: { status: HotKeyAPI.SourcePlatformStatus }) {
  return (
    <Badge variant={status === "available" ? "secondary" : "outline"}>
      {STATUS_LABELS[status]}
    </Badge>
  );
}

function nextAction(platform: HotKeyAPI.SourcePlatformView) {
  const entry =
    platform.capabilities.find(
      (capability) => capability.scheduled.status !== "available",
    )?.scheduled ?? platform.capabilities[0]?.scheduled;
  return entry?.next_action ?? "打开来源查看连接设置。";
}

function EntryPoint({
  label,
  value,
}: {
  label: string;
  value: HotKeyAPI.SourceEntryPointView;
}) {
  return (
    <UI.Content className="flex flex-col gap-2">
      <UI.Content className="flex flex-wrap items-center gap-2">
        <UI.Text className="font-medium">{label}</UI.Text>
        <SourceStatus status={value.status} />
      </UI.Content>
      <UI.Text className="text-muted-foreground text-sm leading-6">
        {value.next_action}
      </UI.Text>
      <UI.Content as="dl" className="grid gap-2 text-sm">
        <UI.Content>
          <UI.Content as="dt" className="text-muted-foreground">
            最近检查
          </UI.Content>
          <UI.Content as="dd">{coverageTime(value.last_checked_at)}</UI.Content>
        </UI.Content>
        <UI.Content>
          <UI.Content as="dt" className="text-muted-foreground">
            最近持久成功
          </UI.Content>
          <UI.Content as="dd">
            {coverageTime(value.last_persisted_success_at)}
          </UI.Content>
        </UI.Content>
        {value.stop_reason ? (
          <UI.Content>
            <UI.Content as="dt" className="text-muted-foreground">
              停止原因
            </UI.Content>
            <UI.Content as="dd">{value.stop_reason}</UI.Content>
          </UI.Content>
        ) : null}
      </UI.Content>
    </UI.Content>
  );
}

export function SourceSettings() {
  const [platforms, setPlatforms] = useState<
    HotKeyAPI.SourcePlatformView[] | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [readFailed, setReadFailed] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const origin = useRef<HTMLButtonElement | null>(null);
  const selected = platforms?.find(
    (platform) => platform.source_key === selectedKey,
  );

  const read = useCallback(
    (current: AbortController) =>
      listSourceCapabilities({ signal: current.signal })
        .then((page) => {
          if (!current.signal.aborted) setPlatforms(page.items);
        })
        .catch((failure: unknown) => {
          if (
            failure instanceof ApiRequestError &&
            failure.kind === "cancelled"
          )
            return;
          if (current.signal.aborted) return;
          setReadFailed(true);
          toast.error(
            failure instanceof ApiRequestError
              ? `${failure.message}${failure.requestId ? ` 请求编号：${failure.requestId}` : ""}`
              : "来源状态加载失败，请重试。",
          );
        })
        .finally(() => {
          if (!current.signal.aborted) setLoading(false);
        }),
    [],
  );

  const refresh = useCallback(async () => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setLoading(true);
    setReadFailed(false);
    await read(current);
  }, [read]);

  useEffect(() => {
    const current = new AbortController();
    controller.current = current;
    void read(current);
    return () => controller.current?.abort();
  }, [read]);

  return (
    <UI.Content
      as="section"
      aria-labelledby="source-settings-heading"
      className="flex flex-col gap-6"
    >
      <UI.Content className="flex flex-wrap items-start justify-between gap-4">
        <UI.Content className="flex flex-col gap-2">
          <UI.Heading
            level={2}
            id="source-settings-heading"
            className="text-xl font-medium"
          >
            我的来源
          </UI.Heading>
          <UI.Text className="text-muted-foreground max-w-2xl text-sm leading-6">
            选择来源管理连接。可用状态以当前连接的实际采集记录为准。
          </UI.Text>
        </UI.Content>
        <Button
          variant="outline"
          size="sm"
          disabled={loading}
          onClick={() => void refresh()}
        >
          <RotateCcwIcon data-icon="inline-start" />
          {loading && platforms ? "正在刷新…" : "刷新状态"}
        </Button>
      </UI.Content>
      {readFailed ? (
        <Alert variant="destructive">
          <AlertTitle>暂时无法读取来源状态</AlertTitle>
          <AlertDescription>
            <UI.Text>请重新加载来源状态。</UI.Text>
            {platforms ? (
              <UI.Text>当前显示上次读取的状态，请重新加载后再核对。</UI.Text>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              disabled={loading}
              onClick={() => void refresh()}
            >
              重新加载
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      {platforms === null && loading ? (
        <UI.Content
          aria-label="正在读取来源设置"
          className="flex flex-col gap-3"
        >
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </UI.Content>
      ) : null}
      {platforms?.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>暂无来源目录</EmptyTitle>
            <EmptyDescription>目录中尚无来源，请稍后刷新。</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}
      {platforms?.length ? (
        <UI.Content className="grid gap-4 sm:grid-cols-2">
          {platforms.map((platform) => (
            <Card key={platform.source_key}>
              <CardHeader>
                <CardTitle asChild>
                  <UI.Heading level={3}>{platform.display_name}</UI.Heading>
                </CardTitle>
                <CardDescription>
                  <UI.Content className="flex flex-col gap-3">
                    <SourceStatus status={platform.status} />
                    <UI.Text className="leading-6">
                      {nextAction(platform)}
                    </UI.Text>
                  </UI.Content>
                </CardDescription>
                <CardAction>
                  <Button
                    variant="outline"
                    size="sm"
                    aria-label={`管理${platform.display_name}`}
                    onClick={(event) => {
                      origin.current = event.currentTarget;
                      setSelectedKey(platform.source_key);
                    }}
                  >
                    管理
                  </Button>
                </CardAction>
              </CardHeader>
            </Card>
          ))}
        </UI.Content>
      ) : null}
      <Sheet
        open={selectedKey !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedKey(null);
        }}
      >
        <SheetContent
          showCloseButton={false}
          className="overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-xl"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            origin.current?.focus();
          }}
        >
          <SheetHeader className="pr-14">
            <SheetTitle>{selected?.display_name ?? "来源设置"}</SheetTitle>
            <SheetDescription>
              管理连接，或查看每项能力的验证记录。
            </SheetDescription>
          </SheetHeader>
          <SheetClose asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              className="absolute top-3 right-3"
              aria-label="关闭来源设置"
            >
              <XIcon data-icon="inline-start" />
            </Button>
          </SheetClose>
          {selected ? (
            <Tabs
              key={selected.source_key}
              defaultValue="connection"
              className="gap-6 px-4 pb-8"
            >
              <TabsList variant="line" aria-label="来源详情">
                <TabsTrigger value="connection">连接设置</TabsTrigger>
                <TabsTrigger value="capabilities">能力详情</TabsTrigger>
              </TabsList>
              <TabsContent value="connection" className="flex flex-col gap-6">
                <SourceStatus status={selected.status} />
                <UI.Text className="text-muted-foreground leading-6">
                  {nextAction(selected)}
                </UI.Text>
                <SourceConnectionActions
                  key={selected.source_key}
                  platform={selected}
                  onChanged={refresh}
                />
                <Separator />
                <UI.Content as="dl" className="flex flex-col gap-4 text-sm">
                  <UI.Content>
                    <UI.Content as="dt" className="text-muted-foreground">
                      连接版本
                    </UI.Content>
                    <UI.Content as="dd">
                      {selected.connection_version === null
                        ? "尚未配置"
                        : `v${selected.connection_version}`}
                    </UI.Content>
                  </UI.Content>
                  <UI.Content>
                    <UI.Content as="dt" className="text-muted-foreground">
                      允许访问的域名
                    </UI.Content>
                    <UI.Content as="dd" className="break-all">
                      {selected.allowed_hosts.length
                        ? selected.allowed_hosts.join("、")
                        : "尚无配置"}
                    </UI.Content>
                  </UI.Content>
                </UI.Content>
              </TabsContent>
              <TabsContent value="capabilities" className="flex flex-col gap-6">
                <UI.Text className="text-muted-foreground leading-6">
                  手动与定时入口分别验证。连接配置完成后，仍需采集成功才会显示可用。
                </UI.Text>
                {selected.capabilities.map((capability) => (
                  <UI.Content
                    as="section"
                    key={capability.capability}
                    aria-label={capability.display_name}
                    className="flex flex-col gap-4"
                  >
                    <Separator />
                    <UI.Heading level={3} className="font-medium">
                      {capability.display_name}
                    </UI.Heading>
                    <UI.Content className="grid gap-5 sm:grid-cols-2">
                      <EntryPoint label="手动入口" value={capability.manual} />
                      <EntryPoint
                        label="定时入口"
                        value={capability.scheduled}
                      />
                    </UI.Content>
                  </UI.Content>
                ))}
              </TabsContent>
            </Tabs>
          ) : null}
        </SheetContent>
      </Sheet>
    </UI.Content>
  );
}

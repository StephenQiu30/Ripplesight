"use client";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";

import { toast } from "sonner";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronDownIcon, RotateCcwIcon } from "lucide-react";
import { getReport } from "@/api/ribao";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/request";
import { PrivateExport } from "@/components/reports/private-export";
import { ReportMarkdown } from "./report-markdown";
import { safeHttpUrl } from "./report-links";

type DetailState =
  | { status: "loading" }
  | { status: "ready"; report: HotKeyAPI.ReportDetailView }
  | { status: "not-found" }
  | { status: "error"; message: string };

function reportTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function ReportDetail({ reportId }: { reportId: string }) {
  return <ReportDetailContent key={reportId} reportId={reportId} />;
}

function ReportDetailContent({ reportId }: { reportId: string }) {
  const [state, setState] = useState<DetailState>({ status: "loading" });
  const [retryKey, setRetryKey] = useState(0);
  useEffect(() => {
    const current = new AbortController();
    void getReport({ report_id: reportId }, { signal: current.signal })
      .then((report) => {
        if (!current.signal.aborted) setState({ status: "ready", report });
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (current.signal.aborted) return;
        if (!(error instanceof ApiRequestError && error.status === 404)) {
          toast.error(
            error instanceof ApiRequestError
              ? error.message
              : "报告加载失败，请稍后重试。",
            {
              description:
                error instanceof ApiRequestError && error.requestId
                  ? `请求编号：${error.requestId}`
                  : undefined,
            },
          );
        }
        setState(
          error instanceof ApiRequestError && error.status === 404
            ? { status: "not-found" }
            : {
                status: "error",
                message:
                  error instanceof ApiRequestError
                    ? `${error.message}${error.requestId ? ` 请求编号：${error.requestId}` : ""}`
                    : "报告加载失败，请稍后重试。",
              },
        );
      });
    return () => current.abort();
  }, [reportId, retryKey]);
  const report = state.status === "ready" ? state.report : null;
  return (
    <div>
      <Button asChild variant="ghost" className="mb-8">
        <Link href="/reports">返回报告列表</Link>
      </Button>
      {state.status === "loading" ? (
        <div aria-label="正在读取报告内容" className="flex flex-col gap-5">
          <Skeleton className="h-10 w-2/3" />
          <Skeleton className="h-60 w-full" />
        </div>
      ) : null}
      {state.status === "not-found" ? (
        <Empty className="py-16">
          <EmptyHeader>
            <EmptyTitle>报告不存在</EmptyTitle>
            <EmptyDescription>
              没有找到可读取的报告，请返回列表查看已有报告。
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button asChild>
              <Link href="/reports">查看已有报告</Link>
            </Button>
          </EmptyContent>
        </Empty>
      ) : null}
      {state.status === "error" ? (
        <Alert variant="destructive">
          <AlertTitle>暂时无法读取报告</AlertTitle>
          <AlertDescription>
            <p>请重新加载报告内容。</p>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => {
                setState({ status: "loading" });
                setRetryKey((key) => key + 1);
              }}
            >
              <RotateCcwIcon data-icon="inline-start" />
              重新加载
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      {report ? (
        <>
          <Badge variant="secondary">
            {report.kind === "weekly" ? "周报" : "日报"}
          </Badge>
          <h1 className="mt-4 text-3xl font-medium tracking-tight break-words sm:text-4xl">
            {report.topic_name}
          </h1>
          <p className="text-muted-foreground mt-4 text-sm leading-6">
            {reportTime(report.window_start)} 至 {reportTime(report.window_end)}
          </p>
          <ReportMarkdown report={report} />
          <section className="mt-8 space-y-3" aria-label="私人报告导出">
            <h2 className="text-lg font-medium">导出这版报告</h2>
            <p className="text-muted-foreground text-sm">
              文件保留固定版本与引用；生成和下载均需当前有效的导出许可。
            </p>
            <PrivateExport
              target={{
                kind: "report",
                reportId: report.id,
                reportVersion: report.version,
              }}
            />
          </section>
          <Collapsible className="mt-12">
            <CollapsibleTrigger asChild>
              <Button variant="ghost">
                版本与引用
                <ChevronDownIcon data-icon="inline-end" />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-6 flex flex-col gap-6">
              <dl className="text-muted-foreground grid gap-4 text-sm sm:grid-cols-2">
                <div>
                  <dt>生成版本</dt>
                  <dd className="text-foreground mt-1">
                    第 {report.version} 版 ·{" "}
                    {report.generator === "model" ? "模型版" : "模板版"}
                  </dd>
                </div>
                <div>
                  <dt>资料截止</dt>
                  <dd className="text-foreground mt-1">
                    {reportTime(report.cutoff_at)}
                  </dd>
                </div>
              </dl>
              {report.citations.length ? (
                <section aria-labelledby="report-citations">
                  <h2 id="report-citations" className="font-medium">
                    原帖引用
                  </h2>
                  <ItemGroup className="mt-4 flex flex-col gap-3">
                    {report.citations.map((citation) => {
                      const url = safeHttpUrl(citation.url);
                      return (
                        <Item
                          role="listitem"
                          variant="default"
                          key={citation.citation}
                          className="break-words"
                        >
                          <ItemContent className="min-w-0 gap-3">
                            <span className="text-muted-foreground mr-2">
                              [{citation.citation}]
                            </span>
                            {url ? (
                              <a
                                href={url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="break-all underline underline-offset-4"
                              >
                                {citation.title}
                              </a>
                            ) : (
                              citation.title
                            )}
                          </ItemContent>
                        </Item>
                      );
                    })}
                  </ItemGroup>
                </section>
              ) : null}
            </CollapsibleContent>
          </Collapsible>
        </>
      ) : null}
    </div>
  );
}

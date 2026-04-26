"use client";

import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, formatDate, Hotspot, statusTone } from "@/lib/api";

export function HotspotDetailClient({ id }: { id: string }) {
  const [item, setItem] = useState<Hotspot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Hotspot>(`/api/hotspots/${id}`).then(setItem).catch((err) => setError(err.message));
  }, [id]);

  if (error) return <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</p>;
  if (!item) return <Skeleton className="h-96" />;

  return (
    <div className="grid gap-5 xl:grid-cols-[1.2fr_.8fr]">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0">
              <CardTitle className="text-2xl leading-tight">{item.title}</CardTitle>
              <CardDescription className="mt-2">{item.ai_analysis?.summary || item.snippet || "暂无摘要"}</CardDescription>
            </div>
            <Badge variant={statusTone(item.status)}>{item.status}</Badge>
          </div>
        </CardHeader>
        <CardContent className="grid gap-5">
          <dl className="grid gap-4 md:grid-cols-[140px_1fr]">
            <dt className="font-semibold text-muted-foreground">来源</dt>
            <dd>{item.source?.name || item.source_id}</dd>
            <dt className="font-semibold text-muted-foreground">关键词</dt>
            <dd>{item.keyword?.keyword || "-"}</dd>
            <dt className="font-semibold text-muted-foreground">发布时间</dt>
            <dd>{formatDate(item.published_at || item.fetched_at)}</dd>
            <dt className="font-semibold text-muted-foreground">作者</dt>
            <dd>{item.author || "-"}</dd>
            <dt className="font-semibold text-muted-foreground">原始链接</dt>
            <dd className="min-w-0 truncate">
              <a className="text-primary underline-offset-4 hover:underline" href={item.url} rel="noreferrer" target="_blank">{item.url}</a>
            </dd>
          </dl>
          <Button asChild className="w-fit" variant="secondary">
            <a href={item.url} rel="noreferrer" target="_blank">
              打开原文
              <ExternalLink className="h-4 w-4" />
            </a>
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>AI 分析</CardTitle>
          <CardDescription>真实性、相关性和报告入选依据。</CardDescription>
        </CardHeader>
        <CardContent>
          {item.ai_analysis ? (
            <dl className="grid gap-4">
              <div className="flex items-center justify-between gap-3">
                <dt className="font-semibold text-muted-foreground">真实性</dt>
                <dd><Badge variant={item.ai_analysis.is_real === false ? "destructive" : "success"}>{String(item.ai_analysis.is_real)}</Badge></dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="font-semibold text-muted-foreground">相关性</dt>
                <dd className="font-bold">{item.ai_analysis.relevance_score}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="font-semibold text-muted-foreground">重要性</dt>
                <dd><Badge variant={statusTone(item.ai_analysis.importance)}>{item.ai_analysis.importance}</Badge></dd>
              </div>
              <div className="grid gap-2">
                <dt className="font-semibold text-muted-foreground">理由</dt>
                <dd className="rounded-lg bg-muted p-3 text-sm leading-7">{item.ai_analysis.relevance_reason || "-"}</dd>
              </div>
            </dl>
          ) : (
            <p className="rounded-lg border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">暂无 AI 分析。</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

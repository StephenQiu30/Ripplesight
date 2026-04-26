"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, formatDate, Notification, Page, statusTone } from "@/lib/api";

export function NotificationsClient() {
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Page<Notification>>("/api/notifications")
      .then((page) => setItems(page.items))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Skeleton className="h-80" />;

  return (
    <div className="grid gap-4">
      {error ? <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</p> : null}
      <Card>
        {items.length === 0 ? <p className="p-6 text-sm text-muted-foreground">暂无通知记录。</p> : null}
        {items.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>类型</TableHead>
                <TableHead>渠道</TableHead>
                <TableHead>收件人</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{item.report_id ? "报告" : "事件"}</TableCell>
                  <TableCell>{item.channel}</TableCell>
                  <TableCell className="max-w-xs truncate">{item.recipient || "-"}</TableCell>
                  <TableCell><Badge variant={statusTone(item.status)}>{item.status}</Badge></TableCell>
                  <TableCell>{formatDate(item.sent_at || item.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </Card>
    </div>
  );
}

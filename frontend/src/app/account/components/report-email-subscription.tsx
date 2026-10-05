"use client";
import * as UI from "@/components/ui/content";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  getReportEmailSubscription,
  updateReportEmailSubscription,
} from "@/api/gerenbaogaotongzhi";
import { Item } from "@/components/ui/item";
import { Spinner } from "@/components/ui/spinner";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription } from "@/components/ui/empty";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
} from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";

export function ReportEmailSubscription() {
  const [subscription, setSubscription] =
    useState<HotKeyAPI.ReportEmailSubscriptionView | null>(null);
  const [failed, setFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void getReportEmailSubscription({ signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) {
          setSubscription(value);
          setFailed(false);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setFailed(true);
          toast.error("邮件订阅读取失败，请重试。");
        }
      });
    return () => controller.abort();
  }, [revision]);
  useEffect(() => () => pending.current?.abort(), []);

  async function save(enabled: boolean) {
    if (!subscription || pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    try {
      const updated = await updateReportEmailSubscription(
        {
          operation_id: crypto.randomUUID(),
          expected_revision: subscription.revision,
          enabled,
        },
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setSubscription(updated);
      toast.success(
        enabled
          ? "报告邮件订阅已开启，请在关注主题中选择发送。"
          : "报告邮件订阅已关闭。",
      );
    } catch {
      if (!controller.signal.aborted) {
        toast.error("订阅保存失败，请刷新后重试。");
        setRevision((value) => value + 1);
      }
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        setBusy(false);
      }
    }
  }

  return (
    <UI.Content
      as="section"
      aria-label="报告邮件订阅"
      className="flex max-w-xl flex-col gap-6"
    >
      <UI.Content as="header" className="flex flex-col gap-3">
        <UI.Heading level={2} className="text-2xl font-medium">
          报告通知
        </UI.Heading>
        <UI.Text className="text-muted-foreground text-sm leading-6">
          日报汇总前一天，周报汇总上一周。默认北京时间每天 08:00、周一 08:00
          开始生成，完成后发送。
        </UI.Text>
      </UI.Content>
      {failed ? (
        <Empty>
          <EmptyDescription>暂时无法读取订阅设置。</EmptyDescription>
          <Button
            variant="outline"
            onClick={() => setRevision((value) => value + 1)}
          >
            重试
          </Button>
        </Empty>
      ) : !subscription ? (
        <Item role="status">
          <Spinner />
          正在读取邮件订阅…
        </Item>
      ) : (
        <>
          <UI.Text className="text-sm break-all">
            收件邮箱：{subscription.email || "尚未绑定"}
          </UI.Text>
          {!subscription.email && (
            <UI.Text className="text-muted-foreground text-sm">
              请先在“登录安全”中绑定并验证邮箱。
            </UI.Text>
          )}
          <Field
            orientation="horizontal"
            data-disabled={busy || !subscription.email}
          >
            <FieldContent>
              <FieldLabel htmlFor="report-email-enabled">
                订阅报告邮件
              </FieldLabel>
              <FieldDescription>
                发送到当前账户的已验证邮箱。可随时关闭，更换邮箱后需重新开启。
              </FieldDescription>
            </FieldContent>
            <Switch
              id="report-email-enabled"
              checked={subscription.enabled}
              disabled={busy || !subscription.email}
              onCheckedChange={(value) => void save(value)}
            />
          </Field>
          {!subscription.delivery_available && (
            <UI.Text className="text-muted-foreground text-sm leading-6">
              平台邮件发送服务尚未就绪。订阅偏好可以保存，当前暂不能发送邮件。
            </UI.Text>
          )}
          <Button asChild variant="outline" className="self-start">
            <Link href="/topics">选择需要发送的关注主题</Link>
          </Button>
        </>
      )}
    </UI.Content>
  );
}

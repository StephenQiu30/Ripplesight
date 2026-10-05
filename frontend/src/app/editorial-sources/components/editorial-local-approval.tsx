"use client";
import * as UI from "@/components/ui/content";

import { useEffect, useId, useRef, useState } from "react";
import {
  approveEditorialRsshubSource,
  approveEditorialBodyExtraction,
} from "@/api/bianjilaiyuan";
import { ApiRequestError } from "@/request";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

export function EditorialLocalApproval({
  profile,
  token,
}: {
  profile: HotKeyAPI.EditorialProfileView;
  token: string;
}) {
  const id = useId();
  const configuration = profile.configuration;
  const rsshub = configuration.kind === "rss" ? configuration.rsshub : null;
  const body =
    "body_extraction" in configuration ? configuration.body_extraction : null;
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  const busyRef = useRef(false);
  const operations = useRef(new Map<string, string>());
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  if (!rsshub && !body) return null;

  async function approve(kind: "rsshub" | "body") {
    if (busyRef.current || !profile.configuration_sha256 || !reason.trim())
      return;
    const common = {
      expected_revision: profile.revision,
      configuration_version: profile.configuration_version,
      configuration_sha256: profile.configuration_sha256,
      reason: reason.trim(),
    };
    const review = kind === "rsshub" ? rsshub?.review : body?.review;
    if (!review) {
      setError("当前配置缺少审查证据，请先补齐并保存来源配置。");
      return;
    }
    const key = JSON.stringify({ kind, ...common, review });
    let operationId = operations.current.get(key);
    if (!operationId) {
      operationId = crypto.randomUUID();
      operations.current.set(key, operationId);
    }
    const options = {
      headers: { "X-HotKey-Operator-Token": token, "X-HotKey-CSRF": "1" },
    };
    busyRef.current = true;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      if (kind === "rsshub" && rsshub?.review)
        await approveEditorialRsshubSource(
          { profile_id: profile.id },
          { ...common, review: rsshub.review, operation_id: operationId },
          options,
        );
      else if (kind === "body" && body?.review)
        await approveEditorialBodyExtraction(
          { profile_id: profile.id },
          { ...common, review: body.review, operation_id: operationId },
          options,
        );
      operations.current.delete(key);
      if (mounted.current)
        setResult(
          `${kind === "rsshub" ? "RSSHub 路由" : "正文提取"}审批已记录；执行仍需来源许可、连接、预算和有效租约。`,
        );
    } catch (caught) {
      if (mounted.current)
        setError(
          caught instanceof ApiRequestError
            ? caught.message
            : "审批未确认，请保留输入并读取来源后重试。",
        );
    } finally {
      busyRef.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <UI.Content
      as="section"
      className="space-y-4"
      aria-label="本机采集组件审批"
    >
      <UI.Heading level={2} className="text-xl font-medium">
        本机采集组件审批
      </UI.Heading>
      <UI.Text className="text-muted-foreground text-sm leading-6">
        审查当前配置中的读取、保存、零费用、出口及请求上限依据。提交只登记固定配置的组件审批；不会启用来源或发出采集请求。
      </UI.Text>
      <UI.Text className="text-sm">
        来源修订 {profile.revision} · 配置版本 {profile.configuration_version}
      </UI.Text>
      <Collapsible>
        <CollapsibleTrigger asChild>
          <Button variant="outline">查看固定配置与审查依据</Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <UI.CodeBlock className="bg-muted mt-3 max-h-80 overflow-auto rounded-lg p-3 text-xs">
            {JSON.stringify(
              {
                configuration_sha256: profile.configuration_sha256,
                rsshub_review: rsshub?.review ?? null,
                body_review: body?.review ?? null,
              },
              null,
              2,
            )}
          </UI.CodeBlock>
        </CollapsibleContent>
      </Collapsible>
      <Field>
        <FieldLabel htmlFor={`${id}-reason`}>审批原因</FieldLabel>
        <Textarea
          id={`${id}-reason`}
          value={reason}
          maxLength={1000}
          onChange={(event) => setReason(event.target.value)}
        />
        <FieldDescription>
          证据必须来自实际审查；配置中的声明需独立审批后才能参与执行准入。
        </FieldDescription>
      </Field>
      <UI.Content className="flex flex-wrap gap-3">
        {rsshub && (
          <Button
            variant="outline"
            disabled={
              busy ||
              !token ||
              !reason.trim() ||
              !rsshub.review ||
              !profile.configuration_sha256
            }
            onClick={() => {
              void approve("rsshub");
            }}
          >
            审批 RSSHub 路由
          </Button>
        )}
        {body && (
          <Button
            variant="outline"
            disabled={
              busy ||
              !token ||
              !reason.trim() ||
              !body.review ||
              !profile.configuration_sha256
            }
            onClick={() => {
              void approve("body");
            }}
          >
            审批正文提取
          </Button>
        )}
      </UI.Content>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {result && (
        <Alert>
          <AlertDescription>{result}</AlertDescription>
        </Alert>
      )}
    </UI.Content>
  );
}

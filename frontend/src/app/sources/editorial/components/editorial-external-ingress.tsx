"use client";
import * as UI from "@/components/ui/content";

import { Separator } from "@/components/ui/separator";

import { Item, ItemContent } from "@/components/ui/item";
import { toast } from "sonner";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  getExternalEditorialIngressReceipt,
  ingestExternalEditorialSource,
} from "@/api/bianjilaiyuan";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError } from "@/request";

type Props = {
  profileId: string;
  expectedRevision: number;
  configurationVersion: number;
  enabled: boolean;
};
const statuses: Record<HotKeyAPI.ExternalIngressItem["status"], string> = {
  pending: "等待处理",
  succeeded: "已保存",
  duplicate: "重复",
  rejected: "已拒绝",
};

export function EditorialExternalIngress({
  profileId,
  expectedRevision,
  configurationVersion,
  enabled,
}: Props) {
  const [token, setToken] = useState("");
  const [materials, setMaterials] = useState("[]");
  const [receipt, setReceipt] =
    useState<HotKeyAPI.ExternalIngressReceipt | null>(null);
  const [busy, setBusy] = useState(false);

  const epoch = useRef(0);
  const working = useRef(false);
  const operations = useRef(new Map<string, string>());
  useEffect(
    () => () => {
      epoch.current += 1;
    },
    [],
  );
  const headers = { "X-HotKey-Source-Token": token, "X-HotKey-CSRF": "1" };
  function changeToken(value: string) {
    epoch.current += 1;
    working.current = false;
    setBusy(false);
    setToken(value);
    setReceipt(null);
  }
  async function perform(
    work: () => Promise<HotKeyAPI.ExternalIngressReceipt>,
    operationId?: string,
  ) {
    if (working.current) return;
    const captured = epoch.current;
    working.current = true;
    setBusy(true);

    try {
      const result = await work();
      if (captured === epoch.current) setReceipt(result);
    } catch (cause) {
      if (cause instanceof ApiRequestError && cause.kind === "cancelled")
        return;
      if (captured !== epoch.current) return;
      const unknown =
        cause instanceof ApiRequestError &&
        ["network", "timeout", "protocol"].includes(cause.kind);
      toast.error(
        `${cause instanceof ApiRequestError ? cause.message : "摄入或回执读取失败，请核对输入与授权。"}${unknown && operationId ? ` 受理结果尚未确认，操作编号 ${operationId}；重试相同输入会复用该编号。` : ""}`,
      );
    } finally {
      if (captured === epoch.current) {
        working.current = false;
        setBusy(false);
      }
    }
  }
  function submit() {
    let input: HotKeyAPI.ExternalEditorialInput["materials"];
    try {
      const value: unknown = JSON.parse(materials);
      if (
        !Array.isArray(value) ||
        value.length < 1 ||
        value.length > 50 ||
        new TextEncoder().encode(materials).byteLength > 4_194_304
      )
        throw new Error();
      input = value as HotKeyAPI.ExternalEditorialInput["materials"];
    } catch {
      toast.error(
        "材料必须为 1—50 项 JSON 数组，总体积不能超过 4 MiB（UTF-8）。",
      );
      return;
    }
    const body = {
      expected_revision: expectedRevision,
      configuration_version: configurationVersion,
      materials: input,
    };
    const key = JSON.stringify(body);
    if (!operations.current.has(key))
      operations.current.set(key, crypto.randomUUID());
    const operationId = operations.current.get(key)!;
    void perform(
      () =>
        ingestExternalEditorialSource(
          { profile_id: profileId },
          { ...body, operation_id: operationId },
          { headers },
        ),
      operationId,
    );
  }
  function read() {
    if (!receipt) return;
    void perform(() =>
      getExternalEditorialIngressReceipt(
        { profile_id: profileId, run_id: receipt.run_id },
        { headers },
      ),
    );
  }
  return (
    <UI.Content
      as="section"
      className="flex flex-col gap-y-4 pt-5"
      aria-label="外部材料摄入"
    >
      <Separator />
      <UI.Heading level={3} className="font-medium">
        外部材料摄入
      </UI.Heading>
      <UI.Text className="text-muted-foreground text-sm">
        单批 1—50 项、最多 4
        MiB。专属来源令牌至少32字符，仅保存在当前页面内存中；服务端未配置专用盐、来源许可或访问范围时拒绝受理。任务排队与单项待处理均不表示正文已经保存。
      </UI.Text>
      <Label htmlFor="external-token">来源专属令牌</Label>
      <Input
        id="external-token"
        type="password"
        autoComplete="off"
        minLength={32}
        maxLength={512}
        value={token}
        onChange={(event) => changeToken(event.target.value)}
      />
      <Button
        variant="ghost"
        onClick={() => {
          changeToken("");
          setMaterials("[]");
        }}
      >
        清除来源令牌与回执
      </Button>
      <Label htmlFor="external-materials">材料 JSON 数组</Label>
      <Textarea
        id="external-materials"
        className="min-h-48 font-mono text-sm"
        value={materials}
        onChange={(event) => setMaterials(event.target.value)}
      />
      <Button disabled={busy || token.length < 32 || !enabled} onClick={submit}>
        受理材料摄入
      </Button>
      {receipt ? (
        <UI.Content className="flex flex-col gap-y-3 text-sm">
          <UI.Text>
            本批收到 {receipt.received} 项 · 配置版本{" "}
            {receipt.configuration_version} · 任务 {receipt.job.status}
          </UI.Text>
          <Link
            href={`/jobs/${receipt.job.id}`}
            className="underline underline-offset-4"
          >
            查看任务 {receipt.job.id}
          </Link>
          <UI.Content>
            <Button
              variant="outline"
              disabled={busy || token.length < 32}
              onClick={read}
            >
              读取逐条摄入回执
            </Button>
          </UI.Content>
          <UI.Text className="text-muted-foreground">
            读取仅查看原批次回执，不重发材料、不启动新的摄入任务。
          </UI.Text>
          {receipt.items.map((item) => (
            <Item variant="muted" key={item.index} asChild>
              <UI.Content as="article" className="flex flex-col gap-y-2 p-3">
                <ItemContent className="min-w-0 gap-3">
                  <UI.Text>
                    第 {item.index + 1} 项 · {statuses[item.status]}
                    {item.change ? ` · ${item.change}` : ""}
                    {item.duplicate_of != null
                      ? ` · 同批第 ${item.duplicate_of + 1} 项`
                      : ""}
                    {item.reason ? ` · ${item.reason}` : ""}
                  </UI.Text>
                  {item.identity_key ? (
                    <UI.Text className="break-all">
                      身份 {item.identity_key}
                    </UI.Text>
                  ) : null}
                  {item.content_id ? (
                    <Link
                      href={`/content/${item.content_id}`}
                      className="break-all underline underline-offset-4"
                    >
                      读取材料 {item.content_id}
                    </Link>
                  ) : null}
                  {item.content_version_id ? (
                    <UI.Text className="break-all">
                      固定版本 {item.content_version_id}
                    </UI.Text>
                  ) : null}
                </ItemContent>
              </UI.Content>
            </Item>
          ))}
        </UI.Content>
      ) : null}
    </UI.Content>
  );
}

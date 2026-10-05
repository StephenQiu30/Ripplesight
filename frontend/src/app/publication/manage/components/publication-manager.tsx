"use client";
import * as UI from "@/components/ui/content";

import {
  Item,
  ItemContent,
  ItemGroup,
  ItemDescription,
} from "@/components/ui/item";
import { toast } from "sonner";
import { Checkbox } from "@/components/ui/checkbox";
import {
  SelectLabel,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from "@/components/ui/select";
import { FieldGroup, FieldLabel, Field } from "@/components/ui/field";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import {
  getPublicationRepublishRun,
  listPublicationPolicies,
  overridePublication,
  republishPublicationSource,
  savePublicationSourcePolicy,
} from "@/api/gongkaifabu";
import {
  getPublicationMediaMirrorRun,
  requestPublicationMediaMirror,
} from "@/api/fabumeiti";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiRequestError } from "@/request";

export function publicationError(error: unknown) {
  if (!(error instanceof ApiRequestError))
    return "操作未完成，请重新读取后检查。";
  if (error.status === 403) return "操作员入口尚未启用或缺少写入授权。";
  if (error.status === 401) return "操作员令牌无效。";
  if (error.status === 409)
    return "修订已变化或该操作编号已使用，请重新读取当前版本。";
  return `${error.message}${error.requestId ? `（请求 ${error.requestId}）` : ""}`;
}

export function PublicationManager() {
  const fieldId = useId();

  const [token, setToken] = useState("");
  const [policies, setPolicies] = useState<HotKeyAPI.SourcePolicyView[]>([]);
  const [busy, setBusy] = useState(false);

  const [run, setRun] = useState<HotKeyAPI.RepublishRunView | null>(null);
  const [mediaRun, setMediaRun] = useState<HotKeyAPI.MediaMirrorRunView | null>(
    null,
  );
  const operations = useRef(new Map<string, string>());
  const context = useRef(0);
  useEffect(
    () => () => {
      context.current += 1;
    },
    [],
  );
  function changeToken(value: string) {
    context.current += 1;
    operations.current.clear();
    setToken(value);
    setPolicies([]);
    setRun(null);
    setMediaRun(null);
    setBusy(false);
  }
  function operationId(form: FormData, kind: string) {
    const key = JSON.stringify([kind, [...form.entries()]]);
    const existing = operations.current.get(key);
    if (existing) return existing;
    const id = crypto.randomUUID();
    operations.current.set(key, id);
    return id;
  }
  const headers = { "X-HotKey-Operator-Token": token, "X-HotKey-CSRF": "1" };
  async function action(work: (current: () => boolean) => Promise<void>) {
    const epoch = context.current;
    const current = () => epoch === context.current;
    setBusy(true);

    try {
      await work(current);
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (current()) toast.error(publicationError(error));
    } finally {
      if (current()) setBusy(false);
    }
  }
  return (
    <UI.Content className="mt-8 flex flex-col gap-y-12">
      <UI.Form
        onSubmit={(event) => {
          event.preventDefault();
          void action(async (current) => {
            const policies = await listPublicationPolicies({ headers });
            if (!current()) return;
            setPolicies(policies);
            toast.success("已读取当前策略。");
          });
        }}
      >
        <FieldGroup className="flex flex-row flex-wrap items-end gap-3">
          <Field className="max-w-md min-w-0 flex-1">
            <FieldLabel htmlFor={`${fieldId}-publication-manager-field-1`}>
              操作员令牌
            </FieldLabel>
            <Input
              autoComplete="off"
              type="password"
              value={token}
              onChange={(event) => changeToken(event.target.value)}
              required
              id={`${fieldId}-publication-manager-field-1`}
            />
          </Field>
          <Button disabled={busy || !token}>读取策略</Button>
          <Button
            variant="ghost"
            type="button"
            onClick={() => {
              changeToken("");
              toast.success("已清除内存令牌。");
            }}
          >
            清除令牌
          </Button>
        </FieldGroup>
      </UI.Form>
      {policies.length ? (
        <UI.Content as="section">
          <UI.Heading level={2} className="text-lg font-medium">
            当前来源策略
          </UI.Heading>
          <ItemGroup className="mt-4 flex flex-col gap-y-4">
            {policies.map((policy) => (
              <Item
                role="listitem"
                variant="muted"
                key={policy.source_key}
                className="p-4 leading-7"
              >
                <ItemContent className="min-w-0 gap-3">
                  <UI.Text as="strong">{policy.source_key}</UI.Text> · 修订{" "}
                  {policy.revision} · {policy.participation_mode}
                  <UI.Text>
                    站内全文 {policy.site_fulltext ? "允许" : "关闭"} · 再分发{" "}
                    {policy.syndicate_fulltext ? "允许" : "关闭"} · 索引{" "}
                    {policy.indexable ? "允许" : "关闭"}
                  </UI.Text>
                  <ItemDescription className="line-clamp-none">
                    {policy.license_name} · 延迟 {policy.release_delay_seconds}{" "}
                    秒
                  </ItemDescription>
                </ItemContent>
              </Item>
            ))}
          </ItemGroup>
        </UI.Content>
      ) : null}
      <UI.Content as="section">
        <UI.Heading level={2} className="text-lg font-medium">
          修订来源策略
        </UI.Heading>
        <UI.Text className="text-muted-foreground mt-3 text-sm">
          正文格式由固定材料记录决定，许可策略只控制公开范围与再分发授权。
        </UI.Text>
        <UI.Form
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            void action(async (current) => {
              const policy = await savePublicationSourcePolicy(
                { source_key: String(form.get("source")) },
                {
                  operation_id: operationId(form, "policy"),
                  expected_revision: Number(form.get("revision")),
                  participation_mode: form.get(
                    "participation",
                  ) as HotKeyAPI.SourcePolicyInput["participation_mode"],
                  site_fulltext: form.has("site"),
                  syndicate_fulltext: form.has("syndicate"),
                  indexable: form.has("index"),
                  release_delay_seconds: Number(form.get("delay")),
                  license_name: String(form.get("license")),
                  license_url: String(form.get("license_url")) || null,
                  reason: String(form.get("reason")),
                },
                { headers },
              );
              if (!current()) return;
              setPolicies((old) => [
                ...old.filter((item) => item.source_key !== policy.source_key),
                policy,
              ]);
              toast.success(
                `策略已保存为修订 ${policy.revision}；增加权限需另受理重建。`,
              );
            });
          }}
        >
          <FieldGroup className="mt-5 grid gap-4 sm:grid-cols-2">
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-2`}>
                来源标识
              </FieldLabel>
              <Input
                name="source"
                required
                maxLength={64}
                id={`${fieldId}-publication-manager-field-2`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-3`}>
                预期修订（新来源为 0）
              </FieldLabel>
              <Input
                name="revision"
                type="number"
                min={0}
                required
                defaultValue={0}
                id={`${fieldId}-publication-manager-field-3`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-4`}>
                参与模式
              </FieldLabel>
              <Select name="participation" defaultValue="isolated">
                <SelectTrigger
                  id={`${fieldId}-publication-manager-field-4`}
                  className="w-full min-w-0"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent position="popper">
                  <SelectGroup>
                    <SelectLabel className="sr-only">参与模式</SelectLabel>
                    <SelectItem value="isolated" className="whitespace-normal">
                      隔离
                    </SelectItem>
                    <SelectItem value="editorial" className="whitespace-normal">
                      编辑来源
                    </SelectItem>
                    <SelectItem
                      value="hot_signal"
                      className="whitespace-normal"
                    >
                      热度信号
                    </SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-5`}>
                许可名称
              </FieldLabel>
              <Input
                name="license"
                required
                maxLength={1000}
                id={`${fieldId}-publication-manager-field-5`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-6`}>
                许可说明 URL
              </FieldLabel>
              <Input
                name="license_url"
                type="url"
                id={`${fieldId}-publication-manager-field-6`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-7`}>
                公开延迟（秒）
              </FieldLabel>
              <Input
                name="delay"
                type="number"
                min={0}
                max={3600}
                defaultValue={180}
                required
                id={`${fieldId}-publication-manager-field-7`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-8`}>
                修订原因
              </FieldLabel>
              <Input
                name="reason"
                required
                maxLength={1000}
                id={`${fieldId}-publication-manager-field-8`}
              />
            </Field>
            <UI.Content className="flex flex-wrap gap-5 text-sm sm:col-span-2">
              <Field orientation="horizontal" className="w-auto">
                <Checkbox
                  name="site"
                  id={`${fieldId}-publication-manager-field-9`}
                />
                <FieldLabel htmlFor={`${fieldId}-publication-manager-field-9`}>
                  允许站内全文
                </FieldLabel>
              </Field>
              <Field orientation="horizontal" className="w-auto">
                <Checkbox
                  name="syndicate"
                  id={`${fieldId}-publication-manager-field-10`}
                />
                <FieldLabel htmlFor={`${fieldId}-publication-manager-field-10`}>
                  允许全文再分发
                </FieldLabel>
              </Field>
              <Field orientation="horizontal" className="w-auto">
                <Checkbox
                  name="index"
                  id={`${fieldId}-publication-manager-field-11`}
                />
                <FieldLabel htmlFor={`${fieldId}-publication-manager-field-11`}>
                  允许索引
                </FieldLabel>
              </Field>
            </UI.Content>
            <Button disabled={busy || !token} className="justify-self-start">
              保存策略修订
            </Button>
          </FieldGroup>
        </UI.Form>
      </UI.Content>
      <UI.Content as="section">
        <UI.Heading level={2} className="text-lg font-medium">
          重建来源公开投影
        </UI.Heading>
        <UI.Form
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            void action(async (current) => {
              const result = await republishPublicationSource(
                { source_key: String(form.get("source")) },
                {
                  operation_id: operationId(form, "republish"),
                  expected_policy_revision: Number(form.get("revision")),
                },
                { headers },
              );
              if (!current()) return;
              setRun(result);
              toast.success("已受理重建任务；不重新抓取来源或调用模型。");
            });
          }}
        >
          <FieldGroup className="mt-5 flex flex-row flex-wrap items-end gap-3">
            <Field className="min-w-0 flex-1 basis-full sm:basis-48">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-12`}>
                来源
              </FieldLabel>
              <Input
                name="source"
                required
                id={`${fieldId}-publication-manager-field-12`}
              />
            </Field>
            <Field className="min-w-0 flex-1 basis-full sm:basis-48">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-13`}>
                策略修订
              </FieldLabel>
              <Input
                name="revision"
                type="number"
                min={1}
                required
                id={`${fieldId}-publication-manager-field-13`}
              />
            </Field>
            <Button disabled={busy || !token}>受理重建</Button>
          </FieldGroup>
        </UI.Form>
        {run ? (
          <UI.Content className="mt-5 flex flex-col gap-y-3 text-sm">
            <UI.Text>
              状态 {run.status} · 已处理 {run.processed_count} 条
              {run.failure_code ? ` · ${run.failure_code}` : ""}
            </UI.Text>
            <Link href={`/jobs/${run.job_id}`} className="underline">
              查看任务与取消入口
            </Link>
            <Button
              className="ml-4"
              variant="outline"
              disabled={busy}
              onClick={() =>
                void action(async (current) => {
                  const result = await getPublicationRepublishRun(
                    { run_id: run.id },
                    { headers },
                  );
                  if (current()) setRun(result);
                })
              }
            >
              读取进度
            </Button>
          </UI.Content>
        ) : null}
      </UI.Content>
      <UI.Content as="section">
        <UI.Heading level={2} className="text-lg font-medium">
          调整单篇公开范围
        </UI.Heading>
        <UI.Form
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            void action(async (current) => {
              const receipt = await overridePublication(
                { content_id: String(form.get("content")) },
                {
                  operation_id: operationId(form, "override"),
                  expected_revision: Number(form.get("revision")),
                  visibility: form.get(
                    "visibility",
                  ) as HotKeyAPI.PublicationOverrideInput["visibility"],
                  seo_indexed: form.has("indexed"),
                  seo_excluded: form.has("excluded"),
                  reason: String(form.get("reason")),
                },
                { headers },
              );
              if (!current()) return;
              toast.success(
                `公开范围已修订为 ${receipt.visibility}，修订 ${receipt.revision}。`,
              );
            });
          }}
        >
          <FieldGroup className="mt-5 grid gap-4 sm:grid-cols-2">
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-14`}>
                条目编号
              </FieldLabel>
              <Input
                name="content"
                required
                id={`${fieldId}-publication-manager-field-14`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-15`}>
                预期公开修订
              </FieldLabel>
              <Input
                name="revision"
                type="number"
                min={1}
                required
                id={`${fieldId}-publication-manager-field-15`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-16`}>
                范围
              </FieldLabel>
              <Select name="visibility" defaultValue="public">
                <SelectTrigger
                  id={`${fieldId}-publication-manager-field-16`}
                  className="w-full min-w-0"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent position="popper">
                  <SelectGroup>
                    <SelectLabel className="sr-only">范围</SelectLabel>
                    <SelectItem value="public" className="whitespace-normal">
                      公开
                    </SelectItem>
                    <SelectItem
                      value="summary-only"
                      className="whitespace-normal"
                    >
                      摘要
                    </SelectItem>
                    <SelectItem value="withdrawn" className="whitespace-normal">
                      撤回
                    </SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-17`}>
                原因
              </FieldLabel>
              <Input
                name="reason"
                required
                maxLength={1000}
                id={`${fieldId}-publication-manager-field-17`}
              />
            </Field>
            <UI.Content className="flex flex-wrap gap-5 text-sm sm:col-span-2">
              <Field orientation="horizontal" className="w-auto">
                <Checkbox
                  name="indexed"
                  id={`${fieldId}-publication-manager-field-18`}
                />
                <FieldLabel htmlFor={`${fieldId}-publication-manager-field-18`}>
                  允许索引
                </FieldLabel>
              </Field>
              <Field orientation="horizontal" className="w-auto">
                <Checkbox
                  name="excluded"
                  id={`${fieldId}-publication-manager-field-19`}
                />
                <FieldLabel htmlFor={`${fieldId}-publication-manager-field-19`}>
                  从索引排除
                </FieldLabel>
              </Field>
            </UI.Content>
            <Button disabled={busy || !token} className="justify-self-start">
              保存范围修订
            </Button>
          </FieldGroup>
        </UI.Form>
      </UI.Content>
      <UI.Content as="section">
        <UI.Heading level={2} className="text-lg font-medium">
          保存已许可正文的媒体
        </UI.Heading>
        <UI.Text className="text-muted-foreground mt-3 text-sm leading-7">
          只保存当前固定正文中的正式图片或视频。同版本和许可修订复用已有任务；不确定、失败或取消的任务需人工核查，不能重复下载。
        </UI.Text>
        <UI.Form
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            void action(async (current) => {
              const result = await requestPublicationMediaMirror(
                { content_id: String(form.get("content")) },
                {
                  operation_id: operationId(form, "media"),
                  content_version_id: String(form.get("version")),
                  policy_revision: Number(form.get("revision")),
                },
                { headers },
              );
              if (!current()) return;
              setMediaRun(result);
              toast.success(
                "已读取媒体任务回执，实际请求仍受网络开关和持久预算控制。",
              );
            });
          }}
        >
          <FieldGroup className="mt-5 grid gap-4 sm:grid-cols-2">
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-20`}>
                条目编号
              </FieldLabel>
              <Input
                name="content"
                required
                id={`${fieldId}-publication-manager-field-20`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-21`}>
                固定正文版本编号
              </FieldLabel>
              <Input
                name="version"
                required
                id={`${fieldId}-publication-manager-field-21`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-22`}>
                当前许可策略修订
              </FieldLabel>
              <Input
                name="revision"
                type="number"
                min={1}
                required
                id={`${fieldId}-publication-manager-field-22`}
              />
            </Field>
            <Button
              disabled={busy || !token}
              className="self-end justify-self-start"
            >
              受理媒体任务
            </Button>
          </FieldGroup>
        </UI.Form>
        <UI.Form
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            void action(async (current) => {
              const result = await getPublicationMediaMirrorRun(
                { run_id: String(form.get("run")) },
                { headers },
              );
              if (current()) setMediaRun(result);
            });
          }}
        >
          <FieldGroup className="mt-5 flex flex-row flex-wrap items-end gap-3">
            <Field className="min-w-0 flex-1 basis-full sm:basis-48">
              <FieldLabel htmlFor={`${fieldId}-publication-manager-field-23`}>
                媒体任务回执编号
              </FieldLabel>
              <Input
                name="run"
                required
                id={`${fieldId}-publication-manager-field-23`}
              />
            </Field>
            <Button disabled={busy || !token} variant="outline">
              读取媒体回执
            </Button>
          </FieldGroup>
        </UI.Form>
        {mediaRun ? (
          <UI.Content className="mt-5 flex flex-col gap-y-3 text-sm">
            <UI.Text>
              状态 {mediaRun.status} · 可用 {mediaRun.available_count}/
              {mediaRun.candidate_count}
              {mediaRun.reason ? ` · ${mediaRun.reason}` : ""}
              {mediaRun.replayed ? " · 已复用同版本任务" : ""}
            </UI.Text>
            <Link href={`/jobs/${mediaRun.job_id}`} className="underline">
              查看媒体任务与取消入口
            </Link>
            <Button
              className="ml-4"
              variant="outline"
              disabled={busy || !token}
              onClick={() =>
                void action(async (current) => {
                  const result = await getPublicationMediaMirrorRun(
                    { run_id: mediaRun.id },
                    { headers },
                  );
                  if (current()) setMediaRun(result);
                })
              }
            >
              读取媒体进度
            </Button>
          </UI.Content>
        ) : null}
      </UI.Content>
    </UI.Content>
  );
}

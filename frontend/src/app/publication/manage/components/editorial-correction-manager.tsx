"use client";
import { Textarea } from "@/components/ui/textarea";
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
import { useId, useRef, useState } from "react";
import {
  correctEditorialRun,
  getCurrentEditorialRun,
  requestEditorialRun,
} from "@/api/bianjifenxi";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { publicationError } from "./publication-manager";

const FIELDS = [
  "selected",
  "title_zh",
  "summary_zh",
  "category",
  "reason_zh",
  "tags",
  "silent",
] as const;
type Field = (typeof FIELDS)[number];
const LABELS: Record<Field, string> = {
  selected: "精选",
  title_zh: "中文标题",
  summary_zh: "中文摘要",
  category: "分类",
  reason_zh: "公开推荐理由",
  tags: "标签",
  silent: "静默推送",
};

export function EditorialCorrectionManager({
  initialContentId = "",
}: {
  initialContentId?: string;
}) {
  const fieldId = useId();

  const [token, setToken] = useState("");
  const [contentId, setContentId] = useState(initialContentId);
  const [run, setRun] = useState<HotKeyAPI.EditorialRunView | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const context = useRef(0);
  const operations = useRef(new Map<string, string>());
  const headers = { "X-HotKey-Operator-Token": token, "X-HotKey-CSRF": "1" };
  function changed(change: () => void) {
    context.current += 1;
    setRun(null);
    setMessage("");
    setBusy(false);
    change();
  }
  async function action(
    work: () => Promise<HotKeyAPI.EditorialRunView>,
    success: string,
  ) {
    const epoch = context.current;
    setBusy(true);
    setMessage("");
    try {
      const next = await work();
      if (epoch === context.current) {
        setRun(next);
        setMessage(success);
      }
    } catch (error) {
      if (epoch === context.current) setMessage(publicationError(error));
    } finally {
      if (epoch === context.current) setBusy(false);
    }
  }
  function save(form: FormData, clear: boolean) {
    if (!run) return;
    const reason = String(form.get("reason") ?? "").trim();
    if (!reason) {
      setMessage("请填写本次纠正原因。");
      return;
    }
    const body: HotKeyAPI.EditorialOverrideInput = {
      operation_id: "",
      expected_manual_version: run.manual_version,
      action: clear ? "clear" : "replace",
      reason,
    };
    if (!clear) {
      const clearFields: Field[] = [];
      for (const field of FIELDS) {
        const mode = form.get(`${field}_mode`);
        if (mode === "clear") clearFields.push(field);
        if (mode !== "replace") continue;
        if (field === "selected" || field === "silent")
          body[field] = form.get(field) === "true";
        else if (field === "tags")
          body.tags = String(form.get(field) ?? "")
            .split(/[,，、\n]/)
            .map((v) => v.trim())
            .filter(Boolean);
        else if (field === "category") {
          const category = form.get(field);
          if (
            category === "ai-models" ||
            category === "ai-products" ||
            category === "industry" ||
            category === "paper" ||
            category === "tip" ||
            category === "opinion"
          )
            body.category = category;
        } else body[field] = String(form.get(field) ?? "").trim();
      }
      body.clear_fields = clearFields;
    }
    const key = JSON.stringify([run.id, body]);
    let operation = operations.current.get(key);
    if (!operation) {
      operation = crypto.randomUUID();
      operations.current.set(key, operation);
    }
    body.operation_id = operation;
    void action(
      () => correctEditorialRun({ run_id: run.id }, body, { headers }),
      clear
        ? "已恢复原自动结果，保留人工修订历史。"
        : "已保存人工字段；其他字段保持原值。",
    );
  }
  function rerun() {
    if (!run) return;
    const key = JSON.stringify([
      "rerun",
      run.id,
      run.content_version_id,
      run.manual_version,
    ]);
    let operation = operations.current.get(key);
    if (!operation) {
      operation = crypto.randomUUID();
      operations.current.set(key, operation);
    }
    void action(
      () =>
        requestEditorialRun(
          { content_id: run.content_id, source_key: run.source_key },
          {
            operation_id: operation,
            content_version_id: run.content_version_id,
            expected_manual_version: run.manual_version,
            stages: "all",
          },
          { headers },
        ),
      "已排队，模型结果完成后再读取当前分析。",
    );
  }
  return (
    <section className="mt-12 flex flex-col gap-y-5">
      <h2 className="text-lg font-medium">精选与中文文案纠正</h2>
      <p className="text-muted-foreground text-sm leading-7">
        按当前人工版本修改或清除字段。静默仅停止新的精选通知；恢复自动结果复用原模型结果。
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void action(
            () =>
              getCurrentEditorialRun({ content_id: contentId }, { headers }),
            "已读取当前分析。",
          );
        }}
      >
        <FieldGroup className="grid gap-4 sm:grid-cols-2">
          <Field className="min-w-0">
            <FieldLabel
              htmlFor={`${fieldId}-editorial-correction-manager-field-1`}
            >
              操作员令牌
            </FieldLabel>
            <Input
              type="password"
              autoComplete="off"
              value={token}
              onChange={(event) => changed(() => setToken(event.target.value))}
              required
              id={`${fieldId}-editorial-correction-manager-field-1`}
            />
          </Field>
          <Field className="min-w-0">
            <FieldLabel
              htmlFor={`${fieldId}-editorial-correction-manager-field-2`}
            >
              作品编号
            </FieldLabel>
            <Input
              value={contentId}
              onChange={(event) =>
                changed(() => setContentId(event.target.value))
              }
              required
              id={`${fieldId}-editorial-correction-manager-field-2`}
            />
          </Field>
          <div className="flex gap-3 sm:col-span-2">
            <Button disabled={busy || !token}>读取当前分析</Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() =>
                changed(() => {
                  setToken("");
                  operations.current.clear();
                })
              }
            >
              清除令牌
            </Button>
          </div>
        </FieldGroup>
      </form>
      {message ? (
        <p role="status" className="bg-muted rounded-md p-4 text-sm leading-7">
          {message}
        </p>
      ) : null}
      {run ? (
        <form
          key={`${run.id}:${run.manual_version}`}
          onSubmit={(event) => {
            event.preventDefault();
            save(new FormData(event.currentTarget), false);
          }}
        >
          <FieldGroup className="flex flex-col gap-y-4">
            <p className="text-sm">
              人工版本 {run.manual_version} ·{" "}
              {run.result?.manual ? "人工覆盖" : "自动结果"} · {run.status}
            </p>
            {run.job_id ? (
              <Link
                href={`/jobs/${run.job_id}`}
                className="text-sm underline underline-offset-4"
              >
                查看分析任务
              </Link>
            ) : null}
            {FIELDS.map((field) => (
              <div key={field} className="grid min-w-0 gap-3 sm:grid-cols-3">
                <FieldLabel htmlFor={`correction-${field}`}>
                  {LABELS[field]}
                </FieldLabel>
                <Select name={`${field}_mode`} defaultValue="keep">
                  <SelectTrigger
                    aria-label={`${LABELS[field]}操作`}
                    className="w-full min-w-0"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent position="popper">
                    <SelectGroup>
                      <SelectLabel className="sr-only">
                        {LABELS[field]}
                      </SelectLabel>
                      <SelectItem value="keep" className="whitespace-normal">
                        保持当前
                      </SelectItem>
                      <SelectItem value="replace" className="whitespace-normal">
                        人工覆盖
                      </SelectItem>
                      <SelectItem value="clear" className="whitespace-normal">
                        恢复自动
                      </SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
                {field === "selected" || field === "silent" ? (
                  <Select
                    name={field}
                    defaultValue={String(run.result?.[field] ?? false)}
                  >
                    <SelectTrigger
                      id={`correction-${field}`}
                      className="w-full min-w-0"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent position="popper">
                      <SelectGroup>
                        <SelectLabel className="sr-only">
                          {LABELS[field]}
                        </SelectLabel>
                        <SelectItem value="true" className="whitespace-normal">
                          开启
                        </SelectItem>
                        <SelectItem value="false" className="whitespace-normal">
                          关闭
                        </SelectItem>
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                ) : field === "category" ? (
                  <Select
                    name={field}
                    defaultValue={
                      run.result?.structure?.category ?? "ai-models"
                    }
                  >
                    <SelectTrigger
                      id={`correction-${field}`}
                      className="w-full min-w-0"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent position="popper">
                      <SelectGroup>
                        <SelectLabel className="sr-only">
                          {LABELS[field]}
                        </SelectLabel>
                        <SelectItem
                          value="ai-models"
                          className="whitespace-normal"
                        >
                          AI 模型
                        </SelectItem>
                        <SelectItem
                          value="ai-products"
                          className="whitespace-normal"
                        >
                          AI 产品
                        </SelectItem>
                        <SelectItem
                          value="industry"
                          className="whitespace-normal"
                        >
                          行业
                        </SelectItem>
                        <SelectItem value="paper" className="whitespace-normal">
                          论文
                        </SelectItem>
                        <SelectItem value="tip" className="whitespace-normal">
                          技巧
                        </SelectItem>
                        <SelectItem
                          value="opinion"
                          className="whitespace-normal"
                        >
                          观点
                        </SelectItem>
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                ) : field === "summary_zh" || field === "reason_zh" ? (
                  <Textarea
                    id={`correction-${field}`}
                    name={field}
                    defaultValue={run.result?.writing?.[field] ?? ""}
                    maxLength={field === "summary_zh" ? 4000 : 400}
                    className="min-w-0 p-2"
                    rows={4}
                  />
                ) : (
                  <Input
                    id={`correction-${field}`}
                    name={field}
                    defaultValue={
                      field === "title_zh"
                        ? (run.result?.writing?.title_zh ?? "")
                        : (
                            run.result?.tags_override ??
                            run.result?.structure?.tags ??
                            []
                          ).join("、")
                    }
                    maxLength={field === "title_zh" ? 200 : 1600}
                  />
                )}
              </div>
            ))}
            <Field className="min-w-0">
              <FieldLabel
                htmlFor={`${fieldId}-editorial-correction-manager-field-3`}
              >
                纠正原因
              </FieldLabel>
              <Input
                name="reason"
                required
                maxLength={1000}
                id={`${fieldId}-editorial-correction-manager-field-3`}
              />
            </Field>
            <div className="flex flex-wrap gap-3">
              <Button
                disabled={
                  busy ||
                  !token ||
                  run.status === "queued" ||
                  run.status === "running"
                }
              >
                保存字段
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={
                  busy ||
                  !token ||
                  run.status === "queued" ||
                  run.status === "running" ||
                  run.status === "unknown"
                }
                onClick={rerun}
              >
                重新分析全部阶段
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={busy || !token || !run.result?.manual}
                onClick={(event) => {
                  const form = event.currentTarget.form;
                  if (form) save(new FormData(form), true);
                }}
              >
                全部恢复自动结果
              </Button>
            </div>
          </FieldGroup>
        </form>
      ) : null}
    </section>
  );
}

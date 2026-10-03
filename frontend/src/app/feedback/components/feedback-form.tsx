"use client";
import { FieldGroup, FieldLabel, Field } from "@/components/ui/field";
import { useId, useRef, useState } from "react";
import { submitFeedback } from "@/api/fankui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError } from "@/request";

function readImage(file: File): Promise<HotKeyAPI.ScreenshotInput> {
  if (
    !["image/png", "image/jpeg", "image/webp", "image/gif"].includes(
      file.type,
    ) ||
    file.size > 8 * 1024 * 1024
  )
    return Promise.reject(
      new Error("请选择不超过 8 MiB 的 PNG、JPEG、WebP 或 GIF 图片。"),
    );
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () =>
      resolve({
        mime: file.type as HotKeyAPI.ScreenshotInput["mime"],
        data_base64: String(reader.result).split(",")[1],
      });
    reader.onerror = () => reject(new Error("截图读取失败，请重新选择。"));
    reader.readAsDataURL(file);
  });
}
export function FeedbackForm() {
  const fieldId = useId();

  const [content, setContent] = useState("");
  const [email, setEmail] = useState("");
  const [pageUrl, setPageUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const operation = useRef<{ fingerprint: string; id: string } | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setMessage("");
    try {
      const screenshot = file ? await readImage(file) : null;
      const fingerprint = JSON.stringify([
        content.trim(),
        email.trim(),
        pageUrl.trim(),
        screenshot,
      ]);
      if (operation.current?.fingerprint !== fingerprint)
        operation.current = { fingerprint, id: crypto.randomUUID() };
      const saved = await submitFeedback({
        operation_id: operation.current.id,
        content: content.trim(),
        email: email.trim() || null,
        page_url: pageUrl.trim() || null,
        screenshot,
      });
      setMessage(`反馈已保存，编号 ${saved.id}。`);
      setContent("");
      setEmail("");
      setPageUrl("");
      setFile(null);
      operation.current = null;
    } catch (error) {
      setMessage(
        error instanceof ApiRequestError
          ? error.code === "feedback_rate_limited"
            ? "提交频率过高，请稍后再试；当前内容已保留。"
            : `${error.message}${error.requestId ? `（请求 ${error.requestId}）` : ""}`
          : error instanceof Error && error.message.startsWith("请选择")
            ? error.message
            : "反馈提交失败，请保留当前内容后重试。",
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <form onSubmit={submit}>
      <FieldGroup className="mt-8 grid gap-5">
        <Field className="min-w-0">
          <FieldLabel htmlFor={`${fieldId}-feedback-form-field-1`}>
            反馈内容
          </FieldLabel>
          <Textarea
            aria-label="反馈内容"
            minLength={2}
            maxLength={5000}
            required
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={7}
            id={`${fieldId}-feedback-form-field-1`}
          />
        </Field>
        <Field className="min-w-0">
          <FieldLabel htmlFor={`${fieldId}-feedback-form-field-2`}>
            联系邮箱（可选）
          </FieldLabel>
          <Input
            type="email"
            aria-label="联系邮箱"
            maxLength={200}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            id={`${fieldId}-feedback-form-field-2`}
          />
        </Field>
        <Field className="min-w-0">
          <FieldLabel htmlFor={`${fieldId}-feedback-form-field-3`}>
            相关页面（可选）
          </FieldLabel>
          <Input
            type="url"
            aria-label="相关页面"
            maxLength={500}
            value={pageUrl}
            onChange={(e) => setPageUrl(e.target.value)}
            placeholder="https://"
            id={`${fieldId}-feedback-form-field-3`}
          />
        </Field>
        <Field className="min-w-0">
          <FieldLabel htmlFor={`${fieldId}-feedback-form-field-4`}>
            截图（可选，最多 8 MiB）
          </FieldLabel>
          <Input
            type="file"
            aria-label="反馈截图"
            accept="image/png,image/jpeg,image/webp,image/gif"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            id={`${fieldId}-feedback-form-field-4`}
          />
        </Field>
        {file && (
          <Button type="button" variant="ghost" onClick={() => setFile(null)}>
            移除截图 {file.name}
          </Button>
        )}
        {message && (
          <p role="status" className="text-sm break-words">
            {message}
          </p>
        )}
        <Button type="submit" disabled={pending} className="justify-self-start">
          {pending ? "正在提交" : "提交反馈"}
        </Button>
      </FieldGroup>
    </form>
  );
}

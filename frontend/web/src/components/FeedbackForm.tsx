"use client";

import { useState } from "react";
import { submitFeedback } from "@/lib/api-client";

type Props = {
  targetId: string;
  targetType: "event" | "digest";
};

export function FeedbackForm({ targetId, targetType }: Props) {
  const [feedbackType, setFeedbackType] = useState("favorite");
  const [comment, setComment] = useState("");
  const [state, setState] = useState<"idle" | "success" | "error" | "submitting">("idle");
  const [message, setMessage] = useState("");

  const submit = async () => {
    setState("submitting");
    try {
      await submitFeedback({ target_type: targetType, target_id: targetId, feedback_type: feedbackType, comment: comment || undefined });
      setState("success");
      setMessage("提交成功");
      setComment("");
    } catch {
      setState("error");
      setMessage("提交失败，请稍后重试");
    }
  };

  return (
    <section className="space-y-2 rounded-xl border border-slate-800 p-3">
      <div className="text-sm font-medium">事件反馈</div>
      <div className="grid gap-2 md:grid-cols-2">
        <select
          value={feedbackType}
          onChange={(e) => setFeedbackType(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-950 p-2 text-sm"
        >
          <option value="favorite">收藏</option>
          <option value="ignore">忽略</option>
          <option value="false_positive">误报</option>
        </select>
        <input
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-950 p-2 text-sm"
          placeholder="可选说明"
        />
      </div>
      <button
        onClick={submit}
        disabled={state === "submitting"}
        className="rounded-lg bg-cyan-700 px-3 py-2 text-sm text-white disabled:opacity-50"
      >
        {state === "submitting" ? "提交中..." : "提交反馈"}
      </button>
      {state === "success" || state === "error" ? <div className="text-sm text-slate-200">{message}</div> : null}
    </section>
  );
}

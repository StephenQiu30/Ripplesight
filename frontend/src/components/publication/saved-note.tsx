"use client";
import { useEffect, useId, useState } from "react";
import { PencilIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Content, Text } from "@/components/ui/content";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { editLocalData, savedIds, NOTES_KEY } from "./local-state";

export function readSavedNotes(
  storage: Pick<Storage, "getItem">,
): Record<string, string> {
  const raw: unknown = JSON.parse(storage.getItem(NOTES_KEY) ?? "{}");
  if (!raw || typeof raw !== "object" || Array.isArray(raw))
    throw new Error("备注数据损坏，未覆盖原记录。");
  const entries = Object.entries(raw);
  if (
    entries.length > 500 ||
    entries.some(
      ([key, value]) =>
        !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(
          key,
        ) ||
        typeof value !== "string" ||
        value.length > 2000,
    )
  )
    throw new Error("备注数据损坏，未覆盖原记录。");
  return raw as Record<string, string>;
}
export function SavedNote({
  id,
  compact = false,
}: {
  id: string;
  compact?: boolean;
}) {
  const fieldId = useId();
  const [note, setNote] = useState("");
  const [draft, setDraft] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const read = () => {
      try {
        const value = readSavedNotes(localStorage)[id] ?? "";
        setNote(value);
        setDraft(value);
      } catch {
        toast.error("本机备注暂不可读，原记录已保留。");
      }
    };
    read();
    window.addEventListener("storage", read);
    return () => window.removeEventListener("storage", read);
  }, [id]);
  async function save() {
    setBusy(true);
    try {
      await editLocalData(() => {
        const notes = readSavedNotes(localStorage);
        const ids = savedIds(localStorage);
        if (!ids.includes(id)) throw new Error("请先收藏这条资讯。");
        notes[id] = draft.trim();
        localStorage.setItem(
          NOTES_KEY,
          JSON.stringify(
            Object.fromEntries(
              ids.filter((key) => notes[key]).map((key) => [key, notes[key]]),
            ),
          ),
        );
      });
      setNote(draft.trim());
      setOpen(false);
      toast.success("备注已保存在本机。");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "备注保存失败。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Content layout="stack" className={compact && !note ? "contents" : "gap-2"}>
      {note ? (
        <Content className="bg-muted rounded-lg px-3 py-2">
          <Text
            size="sm"
            tone="muted"
            className="break-words whitespace-pre-wrap"
          >
            {note}
          </Text>
        </Content>
      ) : null}
      <Dialog
        open={open}
        onOpenChange={(value) => {
          setDraft(note);
          setOpen(value);
        }}
      >
        <DialogTrigger asChild>
          <Button
            variant="ghost"
            size={compact ? "icon-sm" : "sm"}
            className={compact ? "absolute top-0 right-0" : "self-start"}
            aria-label={note ? "编辑备注" : "添加备注"}
          >
            <PencilIcon data-icon={compact ? undefined : "inline-start"} />
            {compact ? null : note ? "编辑备注" : "添加备注"}
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>收藏备注</DialogTitle>
            <DialogDescription>
              只保存在当前浏览器，最多 2,000 字。不会复制资讯正文。
            </DialogDescription>
          </DialogHeader>
          <Field>
            <FieldLabel htmlFor={fieldId}>备注</FieldLabel>
            <Textarea
              id={fieldId}
              value={draft}
              maxLength={2000}
              onChange={(event) => setDraft(event.target.value)}
            />
          </Field>
          <Content className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button disabled={busy} onClick={() => void save()}>
              {busy ? "正在保存…" : "保存备注"}
            </Button>
          </Content>
        </DialogContent>
      </Dialog>
    </Content>
  );
}

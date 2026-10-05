"use client";
import * as UI from "@/components/ui/content";

import { Button } from "@/components/ui/button";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { getSelectedPublicationSnapshot } from "@/api/gongkaifabu";

export function SelectedSnapshotDownload() {
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  const download = useRef<{ url: string; timer: number | null } | null>(null);
  const clearDownload = useCallback(() => {
    if (!download.current) return;
    if (download.current.timer !== null)
      window.clearTimeout(download.current.timer);
    URL.revokeObjectURL(download.current.url);
    download.current = null;
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      clearDownload();
    };
  }, [clearDownload]);

  async function downloadSnapshot() {
    if (busy) return;
    setBusy(true);
    try {
      const snapshot = await getSelectedPublicationSnapshot({});
      if (!mounted.current) return;
      clearDownload();
      const blob = new Blob([JSON.stringify(snapshot, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      download.current = { url, timer: null };
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "hotkey-selected-snapshot.json";
      document.body.append(anchor);
      try {
        anchor.click();
      } finally {
        anchor.remove();
        if (download.current)
          download.current.timer = window.setTimeout(clearDownload, 0);
      }
      toast.success("快照已下载。");
    } catch {
      clearDownload();
      if (mounted.current) toast.error("快照暂时无法下载，请重新尝试。");
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <UI.Text as="span" className="inline-flex flex-col items-start gap-2">
      <Button
        type="button"
        disabled={busy}
        onClick={downloadSnapshot}
        variant="link"
        className="justify-start px-0"
      >
        {busy ? "正在读取快照…" : "精选同步快照"}
      </Button>
    </UI.Text>
  );
}

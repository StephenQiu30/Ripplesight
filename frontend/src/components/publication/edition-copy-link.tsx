"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

export function EditionCopyLink({ href }: { href: string }) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      variant="secondary"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await navigator.clipboard.writeText(
            new URL(href, window.location.origin).href,
          );
          toast.success("阅读链接已复制。");
        } catch {
          toast.error("暂时无法复制，请复制浏览器地址。");
        } finally {
          setBusy(false);
        }
      }}
    >
      复制链接
    </Button>
  );
}

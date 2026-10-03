"use client";

import NextImage from "next/image";
import { useEffect, useState } from "react";

import {
  getPublicationItemPosterPng,
  getPublicationStoryPosterPng,
  getPublicationEditionPosterPng,
} from "@/api/gongkaifenfa";
import { Button } from "@/components/ui/button";

type PosterTarget =
  | { contentId: string }
  | { eventId: string }
  | { kind: "daily" | "weekly" | "monthly"; key: string };

export function PosterDownload({ target }: { target: PosterTarget }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );
  return (
    <div>
      <Button
        variant="outline"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setMessage("");
          setPreview(null);
          try {
            const data: unknown =
              "contentId" in target
                ? await getPublicationItemPosterPng(
                    { content_id: target.contentId },
                    { responseType: "blob" },
                  )
                : "eventId" in target
                  ? await getPublicationStoryPosterPng(
                      { event_id: target.eventId },
                      { responseType: "blob" },
                    )
                  : await getPublicationEditionPosterPng(
                      { kind: target.kind, key: target.key },
                      { responseType: "blob" },
                    );
            if (!(data instanceof Blob) || data.type !== "image/png")
              throw new Error("invalid_poster");
            const signature = new Uint8Array(
              await data.slice(0, 8).arrayBuffer(),
            );
            if (
              [137, 80, 78, 71, 13, 10, 26, 10].some(
                (value, index) => signature[index] !== value,
              )
            )
              throw new Error("invalid_poster");
            setPreview(URL.createObjectURL(data));
            setMessage(
              "海报已生成，包含当前阅读地址的二维码，可以预览后下载。",
            );
          } catch {
            setMessage("海报当前不可读取或材料许可已变化，请重新尝试。");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "生成海报…" : "生成海报 PNG"}
      </Button>
      {message ? (
        <p role="status" className="text-muted-foreground mt-2 text-xs">
          {message}
        </p>
      ) : null}
      {preview ? (
        <div className="mt-4 flex flex-col gap-y-3">
          <NextImage
            src={preview}
            alt="资讯海报预览"
            unoptimized
            width={1080}
            height={1440}
            className="h-auto max-w-80 rounded-md"
          />
          <Button asChild variant="outline">
            <a href={preview} download="hotkey-poster.png">
              下载海报 PNG
            </a>
          </Button>
        </div>
      ) : null}
    </div>
  );
}

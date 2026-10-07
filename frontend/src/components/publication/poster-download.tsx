"use client";
import * as UI from "@/components/ui/content";

import NextImage from "next/image";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ApiRequestError } from "@/request";

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
  const [preview, setPreview] = useState<string | null>(null);
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );
  return (
    <UI.Content>
      <Button
        variant="outline"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
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
            toast.success(
              "海报已生成，包含当前阅读地址的二维码，可以预览后下载。",
            );
          } catch (error) {
            if (error instanceof ApiRequestError && error.kind === "cancelled")
              return;
            toast.error("海报当前不可读取或材料许可已变化，请重新尝试。");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "生成海报…" : "生成海报 PNG"}
      </Button>
      {preview ? (
        <UI.Content className="mt-4 flex flex-col gap-y-3">
          <NextImage
            src={preview}
            alt="资讯海报预览"
            unoptimized
            width={1080}
            height={1440}
            className="h-auto max-w-80 rounded-md"
          />
          <Button asChild variant="outline">
            <UI.TextLink href={preview} download="ripplesight-poster.png">
              下载海报 PNG
            </UI.TextLink>
          </Button>
        </UI.Content>
      ) : null}
    </UI.Content>
  );
}

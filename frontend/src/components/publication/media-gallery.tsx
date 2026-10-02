"use client";

import Image from "next/image";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";

// An API projection carries permission; the URL also stays on the exact owned bytes route.
export function ownedMediaUrl(value: string | null | undefined): string | null {
  return value &&
    /^\/api\/publication\/media\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/(?:original|avatar|card|thumb|full|og|avatar-48|avatar-96|image-336|image-720|image-1200|image-1600)\/site$/i.test(
      value,
    )
    ? value
    : null;
}

function thumbnail(media: HotKeyAPI.PublicMediaView): string | null {
  return (
    ownedMediaUrl(
      media.renditions?.find(
        (entry) => entry.mode === "image-336" || entry.mode === "thumb",
      )?.reading_url,
    ) ?? ownedMediaUrl(media.reading_url)
  );
}

export function MediaGallery({
  media,
}: {
  media: HotKeyAPI.PublicMediaView[];
}) {
  const [current, setCurrent] = useState<number | null>(null);
  const [failed, setFailed] = useState<Set<string>>(() => new Set());
  const images = media.filter(
    (entry) =>
      entry.kind === "image" &&
      entry.state === "available" &&
      ownedMediaUrl(entry.reading_url) &&
      !failed.has(entry.key),
  );
  const selected = current === null ? null : (images[current] ?? null);
  const unavailable = (key: string) => {
    setFailed((old) => new Set([...old, key]));
    setCurrent(null);
  };
  function move(delta: number) {
    setCurrent((old) =>
      old === null || !images.length
        ? null
        : (old + delta + images.length) % images.length,
    );
  }
  return (
    <section aria-label="媒体阅读" className="space-y-4">
      <h2 className="text-sm font-medium">媒体</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
        {media.map((entry) => {
          const url =
            entry.state === "available" && !failed.has(entry.key)
              ? ownedMediaUrl(entry.reading_url)
              : null;
          if (url && entry.kind === "image")
            return (
              <button
                key={entry.key}
                type="button"
                className="bg-muted/30 overflow-hidden rounded-md border text-left"
                aria-label={`放大 ${entry.alt || "图片"}`}
                onClick={() =>
                  setCurrent(
                    images.findIndex((image) => image.key === entry.key),
                  )
                }
              >
                <Image
                  src={thumbnail(entry) ?? url}
                  alt={entry.alt || "已保存图片"}
                  width={entry.width ?? 640}
                  height={entry.height ?? 480}
                  unoptimized
                  className="h-auto max-h-56 w-full object-contain"
                  onError={() => unavailable(entry.key)}
                />
              </button>
            );
          if (url && entry.kind === "video")
            return (
              <video
                key={entry.key}
                src={url}
                controls
                preload="metadata"
                playsInline
                aria-label={entry.alt || "已保存视频"}
                className="max-w-full rounded-md"
                onError={() => unavailable(entry.key)}
              />
            );
          if (url && entry.kind === "audio")
            return (
              <audio
                key={entry.key}
                src={url}
                controls
                preload="metadata"
                aria-label={entry.alt || "已保存音频"}
                className="w-full"
                onError={() => unavailable(entry.key)}
              />
            );
          return (
            <p
              key={entry.key}
              className="text-muted-foreground text-xs leading-6"
            >
              <a
                href={entry.original_url}
                target="_blank"
                rel="noreferrer"
                className="underline"
              >
                {entry.alt || "媒体"} · 来源链接 ↗
              </a>
              {failed.has(entry.key) ? " · 当前保存媒体不可读取" : null}
            </p>
          );
        })}
      </div>
      <Dialog
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setCurrent(null);
        }}
      >
        {selected ? (
          <DialogContent
            className="max-w-5xl gap-3"
            onKeyDown={(event) => {
              if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
                event.preventDefault();
                move(event.key === "ArrowLeft" ? -1 : 1);
              }
            }}
          >
            <DialogTitle>{selected.alt || "已保存图片"}</DialogTitle>
            <DialogDescription>
              使用左右方向键切换图片。媒体每次读取都会复核当前材料和许可。
            </DialogDescription>
            <Image
              src={ownedMediaUrl(selected.reading_url)!}
              alt={selected.alt || "已保存图片"}
              width={selected.width ?? 1200}
              height={selected.height ?? 900}
              unoptimized
              className="max-h-[70vh] w-full object-contain"
              onError={() => unavailable(selected.key)}
            />
            <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
              <Button
                size="sm"
                variant="outline"
                onClick={() => move(-1)}
                disabled={images.length < 2}
              >
                上一张
              </Button>
              <span>
                {(current ?? 0) + 1} / {images.length}
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => move(1)}
                disabled={images.length < 2}
              >
                下一张
              </Button>
              <a
                href={ownedMediaUrl(selected.reading_url)!}
                target="_blank"
                rel="noreferrer"
                className="underline"
              >
                读取原尺寸图片
              </a>
            </div>
          </DialogContent>
        ) : null}
      </Dialog>
    </section>
  );
}

"use client";
import * as UI from "@/components/ui/content";

import { UserRoundIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { getIdentityAvatar } from "@/api/identity";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";

export function UserAvatar({
  user,
  className,
  retryable = false,
}: {
  user: HotKeyAPI.IdentityUserView;
  className?: string;
  retryable?: boolean;
}) {
  const hash = user.avatar_sha256;
  const [attempt, setAttempt] = useState(0);
  const [asset, setAsset] = useState<{
    hash: string;
    url?: string;
    failed?: boolean;
  } | null>(null);

  useEffect(() => {
    if (!hash) return;
    const controller = new AbortController();
    let objectUrl: string | undefined;
    getIdentityAvatar(
      { sha256: hash },
      { signal: controller.signal, responseType: "blob" },
    )
      .then((body: unknown) => {
        if (controller.signal.aborted) return;
        if (
          !(body instanceof Blob) ||
          body.size === 0 ||
          body.type !== "image/png"
        )
          throw new Error("Invalid avatar response");
        objectUrl = URL.createObjectURL(body);
        setAsset({ hash, url: objectUrl });
      })
      .catch(() => {
        if (!controller.signal.aborted) setAsset({ hash, failed: true });
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [hash, attempt]);

  const current = asset?.hash === hash ? asset : null;
  return (
    <UI.Content className="flex flex-col items-center gap-2">
      <Avatar className={className}>
        {current?.url && (
          <AvatarImage
            src={current.url}
            alt={`${user.username} 的头像`}
            onLoadingStatusChange={(status) => {
              if (status === "error" && hash) setAsset({ hash, failed: true });
            }}
          />
        )}
        <AvatarFallback
          aria-label={current?.failed ? "头像暂不可用" : "默认用户头像"}
        >
          <UserRoundIcon className="size-1/2" aria-hidden="true" />
        </AvatarFallback>
      </Avatar>
      {retryable && current?.failed && (
        <Button
          type="button"
          variant="link"
          size="sm"
          onClick={() => setAttempt((value) => value + 1)}
        >
          重新加载头像
        </Button>
      )}
    </UI.Content>
  );
}

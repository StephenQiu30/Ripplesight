"use client";

import Link from "next/link";
import type { ComponentProps } from "react";
import { isPublicPagePath, safeReturnTo } from "./access";
import { useLoginDialog } from "./login-context";
import { useIdentitySession } from "./session-context";

export function AuthLink({
  href,
  onClick,
  ...props
}: ComponentProps<typeof Link>) {
  const session = useIdentitySession();
  const showLogin = useLoginDialog();
  return (
    <Link
      {...props}
      href={href}
      onClick={(event) => {
        onClick?.(event);
        if (
          event.defaultPrevented ||
          !showLogin ||
          session ||
          event.button !== 0 ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey ||
          (props.target && props.target !== "_self") ||
          props.download ||
          typeof href !== "string" ||
          !href.startsWith("/") ||
          href.startsWith("//")
        )
          return;
        const destination = new URL(href, window.location.origin);
        if (
          destination.pathname !== "/login" &&
          isPublicPagePath(destination.pathname)
        )
          return;
        event.preventDefault();
        const target =
          destination.pathname === "/login"
            ? (destination.searchParams.get("returnTo") ??
              destination.searchParams.get("return_to") ??
              destination.searchParams.get("next") ??
              `${window.location.pathname}${window.location.search}${window.location.hash}`)
            : `${destination.pathname}${destination.search}${destination.hash}`;
        showLogin(safeReturnTo(target));
      }}
    />
  );
}

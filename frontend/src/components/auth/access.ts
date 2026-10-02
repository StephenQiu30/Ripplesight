export const PUBLIC_PAGE_PATHS = [
  "/",
  "/login",
  "/about",
  "/privacy",
  "/terms",
  "/contact",
  "/changelog",
] as const;

export const SYSTEM_PAGE_PREFIXES = [
  "/topics",
  "/monitors",
  "/events",
  "/content",
  "/hotlists",
  "/discover",
  "/items",
  "/editions",
  "/reports",
  "/sources",
  "/editorial-sources",
  "/operations",
  "/jobs",
  "/leaderboard",
  "/codex-resets",
  "/publication",
  "/site",
  "/agent",
  "/feeds",
  "/feedback",
  "/account",
] as const;

export function isPublicPagePath(pathname: string | null) {
  return PUBLIC_PAGE_PATHS.some((path) => path === pathname);
}

export function safeReturnTo(value?: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//"))
    return "/topics";
  if (/[\\\u0000-\u0020\u007f]/.test(value)) return "/topics";
  try {
    const destination = new URL(value, "https://hotkey.local");
    const decodedPath = decodeURIComponent(destination.pathname);
    if (
      destination.origin !== "https://hotkey.local" ||
      /[\\\u0000-\u0020\u007f]/.test(decodedPath) ||
      decodedPath.startsWith("//") ||
      !SYSTEM_PAGE_PREFIXES.some(
        (prefix) =>
          destination.pathname === prefix ||
          destination.pathname.startsWith(`${prefix}/`),
      )
    )
      return "/topics";
    return `${destination.pathname}${destination.search}${destination.hash}`;
  } catch {
    return "/topics";
  }
}

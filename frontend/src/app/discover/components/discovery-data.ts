import { categories } from "@/components/publication/reading-format";
import { ApiRequestError } from "@/request";

export function discoveryFailure(error: unknown) {
  const known = error instanceof ApiRequestError ? error : null;
  return new ApiRequestError({
    kind: known?.kind ?? "protocol",
    code: known?.code ?? known?.kind ?? "publication_read_failed",
    status: known?.status,
    message: "公开资料读取失败",
  });
}

export type DiscoveryParams = Record<string, string | undefined>;

export function discoveryScope(params: DiscoveryParams): {
  category?: (typeof categories)[number][0];
  mode: "selected" | "all";
  window: "24h" | "7d";
  by: "published" | "timeline";
  channel?: "news" | "x" | "firstParty";
} {
  return {
    category: categories.find(([key]) => key === params.category)?.[0],
    mode: params.mode === "selected" ? ("selected" as const) : ("all" as const),
    window: params.window === "7d" ? ("7d" as const) : ("24h" as const),
    by:
      params.by === "published"
        ? ("published" as const)
        : ("timeline" as const),
    channel:
      params.channel === "news" ||
      params.channel === "x" ||
      params.channel === "firstParty"
        ? params.channel
        : undefined,
  };
}

export function discoveryHref(params: DiscoveryParams, cursor?: string | null) {
  const query = new URLSearchParams(
    Object.entries(params).filter((entry): entry is [string, string] =>
      Boolean(entry[1]),
    ),
  );
  query.delete("cursor");
  if (cursor) query.set("cursor", cursor);
  return query.size ? `/discover?${query}` : "/discover";
}

export function discoverySources(page: HotKeyAPI.PublicItemsPage | null) {
  return (page?.source_status ?? []).map((source) => ({
    key: source.source_key,
    name: source.name,
  }));
}
